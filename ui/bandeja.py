"""
ui/bandeja.py — El ÚNICO icono de Lune en la bandeja del sistema (corte 4).

Antes había hasta cuatro (ventana web, nativa, mascota animada/3D y mascota de
sprites), cada una con su menú corto y estados sin sincronizar. Ahora, como el
SystemTray.cs de Mate-Engine, hay uno solo:

- el menú se RECONSTRUYE en `aboutToShow` con `nucleo.acciones_ui.menu_bandeja`
  (las mismas acciones que el radial y los atajos, por el Despachador), así
  siempre refleja el estado real (voz, modo fantasma, modo juego, tema…);
- solo se usa `triggered` (nunca `toggled` + setChecked programático, que
  dispararía la acción al reconstruir);
- clic izquierdo o doble clic → «Abrir Lune»; clic central → sacar/guardar la
  mascota;
- el tooltip (≤ 127 caracteres, límite de Windows) resume el estado y se
  refresca con `ServiciosEscritorio.estado_cambio` como mucho una vez por segundo;
- red de seguridad: `set_mascota(v)` llama a `v.quitar_bandeja()` por si una
  mascota creada sin `bandeja=False` puso la suya.

Las acciones se ejecutan con un QTimer de 0 ms: el menú termina de cerrarse
antes de que, p. ej., «Salir» destruya la bandeja.
"""
from __future__ import annotations

import copy
import functools
import logging
import time
from typing import Any, Callable, Iterable, List, Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from nucleo import acciones_ui
from nucleo.acciones_ui import ItemMenu

_log = logging.getLogger("lune.bandeja")

TOOLTIP_MAX = 127
PRESETS_RESPALDO = ("cian", "magenta_mate", "violeta", "rojo_neon", "ambar", "verde_acido")


def _cfg(config: Any, seccion: str, clave: str, defecto: Any = None) -> Any:
    try:
        if hasattr(config, "get") and not isinstance(config, dict):
            v = config.get(seccion, clave, defecto)
        else:
            v = (config or {}).get(seccion, {}).get(clave, defecto)
    except Exception:
        return defecto
    return copy.deepcopy(v)


def _presets_tema() -> List[str]:
    """Presets de nucleo/tema.PRESETS (corte 4, agente C) o la lista conocida."""
    try:
        from nucleo import tema
        p = getattr(tema, "PRESETS", None)
        if isinstance(p, dict) and p:
            return [str(k) for k in p]
    except Exception:
        pass
    return list(PRESETS_RESPALDO)


def texto_tooltip(estado: Any) -> str:
    """Resumen del estado para el tooltip de la bandeja (≤ 127 caracteres)."""
    partes = ["Lune CD"]
    if getattr(estado, "juego", False):
        partes.append("modo juego")
    if getattr(estado, "alarma", False):
        partes.append("¡alarma!")
    if getattr(estado, "visible", False):
        partes.append("mascota durmiendo" if getattr(estado, "durmiendo", False) else "mascota fuera")
    if getattr(estado, "llamada", False):
        partes.append("en llamada")
    if getattr(estado, "hablando", False):
        partes.append("hablando")
    elif getattr(estado, "pensando", False):
        partes.append("pensando")
    if getattr(estado, "bailando", ""):
        partes.append("bailando")
    if getattr(estado, "grande", False):
        partes.append("pantalla grande")
    texto = " · ".join(partes)
    return texto if len(texto) <= TOOLTIP_MAX else texto[:TOOLTIP_MAX - 1] + "…"


class BandejaLune(QObject):
    """Un solo QSystemTrayIcon para toda la app (controlador de ServiciosEscritorio)."""

    INTERVALO_TOOLTIP_MS = 1000
    _ICONOS_AVISO = {
        "info": QSystemTrayIcon.MessageIcon.Information,
        "aviso": QSystemTrayIcon.MessageIcon.Warning,
        "warning": QSystemTrayIcon.MessageIcon.Warning,
        "error": QSystemTrayIcon.MessageIcon.Critical,
        "critical": QSystemTrayIcon.MessageIcon.Critical,
    }

    def __init__(self, despachador, estado, contexto: Callable[[], Any], config, *,
                 icono: Optional[QIcon] = None, fabrica_tray=QSystemTrayIcon,
                 parent: Optional[QObject] = None,
                 presets: Optional[Callable[[], Iterable[Any]]] = None,
                 fabrica_menu: Callable[[], QMenu] = QMenu):
        super().__init__(parent)
        self._desp = despachador
        self._estado = estado
        self._contexto = contexto
        self._config = config
        self._icono = icono
        self._fabrica = fabrica_tray
        self._fabrica_menu = fabrica_menu
        self._presets = presets or _presets_tema
        self.icono_tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._submenus: List[QMenu] = []
        self._qss = ""
        self._tooltip = ""
        self._ultimo_tooltip = 0.0
        self._t_tooltip = QTimer(self)
        self._t_tooltip.setSingleShot(True)
        self._t_tooltip.timeout.connect(self._tooltip_ahora)

    # ── Ciclo de vida ──────────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self.icono_tray is not None:
            return
        disponible = getattr(self._fabrica, "isSystemTrayAvailable", None)
        try:
            if callable(disponible) and not disponible():
                _log.info("bandeja: el sistema no tiene bandeja")
                return
        except Exception:
            pass
        try:
            tray = self._fabrica(self._icono if self._icono is not None else QIcon(), self)
        except TypeError:
            tray = self._fabrica()
            if self._icono is not None:
                tray.setIcon(self._icono)
        menu = self._fabrica_menu()
        menu.aboutToShow.connect(self._reconstruir)
        if self._qss:
            menu.setStyleSheet(self._qss)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_activado)
        self.icono_tray, self._menu = tray, menu
        self._reconstruir()                     # algunos sistemas no enseñan un menú vacío
        self._tooltip_ahora()
        tray.show()

    def detener(self) -> None:
        """Quita el icono YA y borra el menú (también en el cambio de interfaz)."""
        self._t_tooltip.stop()
        tray, self.icono_tray = self.icono_tray, None
        menu, self._menu = self._menu, None
        subs, self._submenus = self._submenus, []
        if tray is not None:
            for metodo, args in (("hide", ()), ("setContextMenu", (None,)), ("deleteLater", ())):
                try:
                    getattr(tray, metodo)(*args)
                except (RuntimeError, AttributeError, TypeError):
                    pass
        for m in subs + ([menu] if menu is not None else []):
            try:
                m.deleteLater()
            except (RuntimeError, AttributeError):
                pass

    def set_mascota(self, v) -> None:
        """Red de seguridad: que la mascota no tenga su propio icono."""
        if v is not None:
            f = getattr(v, "quitar_bandeja", None)
            if callable(f):
                try:
                    f()
                except Exception:
                    _log.exception("bandeja: quitar_bandeja de la mascota falló")
        self.refrescar_tooltip()

    # ── Menú ───────────────────────────────────────────────────────────────
    def items(self) -> List[ItemMenu]:
        """Lo que tendría ahora el menú (datos puros de acciones_ui)."""
        est = self._estado.actual() if hasattr(self._estado, "actual") else self._estado()
        ctx = self._contexto()
        rapidas = _cfg(self._config, "bandeja", "acciones", [])
        try:
            presets = list(self._presets())
        except Exception:
            presets = list(PRESETS_RESPALDO)
        return acciones_ui.menu_bandeja(self._desp, est, ctx, rapidas, presets)

    def _reconstruir(self) -> None:
        menu = self._menu
        if menu is None:
            return
        for sm in self._submenus:
            try:
                sm.deleteLater()
            except RuntimeError:
                pass
        self._submenus = []
        menu.clear()
        try:
            items = self.items()
        except Exception:
            _log.exception("bandeja: no pude construir el menú")
            items = [ItemMenu("mostrar_lune", "Abrir Lune", negrita=True), ItemMenu("salir", "Salir")]
        self._poblar(menu, items)

    def _poblar(self, menu: QMenu, items) -> None:
        for it in items:
            if it.separador:
                menu.addSeparator()
                continue
            if it.hijos:
                sub = menu.addMenu(it.etiqueta)
                self._submenus.append(sub)
                if self._qss:
                    sub.setStyleSheet(self._qss)
                self._poblar(sub, it.hijos)
                continue
            act = menu.addAction(it.etiqueta)
            if it.marcado is not None:
                act.setCheckable(True)
                act.setChecked(bool(it.marcado))
            act.setEnabled(bool(it.habilitado))
            if it.negrita:
                f = act.font()
                f.setBold(True)
                act.setFont(f)
            act.setData(f"{it.id}|{it.arg}")
            act.triggered.connect(functools.partial(self._pedir, it.id, it.arg))

    def _pedir(self, id_: str, arg: str = "", *_):
        """`triggered` de una entrada: se ejecuta cuando el menú ya se cerró."""
        QTimer.singleShot(0, functools.partial(self.ejecutar, id_, arg))

    def ejecutar(self, id_: str, arg: str = "") -> bool:
        if not id_:
            return False
        return bool(self._desp.ejecutar(id_, arg, origen="bandeja"))

    def _on_activado(self, razon) -> None:
        R = QSystemTrayIcon.ActivationReason
        if razon in (R.Trigger, R.DoubleClick):
            self.ejecutar("mostrar_lune")
        elif razon == R.MiddleClick:
            self.ejecutar("mascota")

    # ── Tooltip y avisos ───────────────────────────────────────────────────
    def refrescar_tooltip(self) -> None:
        """Pide refrescar el tooltip: como mucho una vez por segundo."""
        if self.icono_tray is None:
            return
        pasado = (time.monotonic() - self._ultimo_tooltip) * 1000
        if pasado >= self.INTERVALO_TOOLTIP_MS:
            self._tooltip_ahora()
        elif not self._t_tooltip.isActive():
            self._t_tooltip.start(max(1, int(self.INTERVALO_TOOLTIP_MS - pasado)))

    def _tooltip_ahora(self) -> None:
        tray = self.icono_tray
        if tray is None:
            return
        self._ultimo_tooltip = time.monotonic()
        try:
            est = self._estado.actual() if hasattr(self._estado, "actual") else self._estado()
            texto = texto_tooltip(est)
        except Exception:
            texto = "Lune CD"
        if texto != self._tooltip:
            self._tooltip = texto
            try:
                tray.setToolTip(texto)
            except RuntimeError:
                pass

    def mostrar_aviso(self, titulo: str, texto: str, ms: int = 4000, tipo: str = "info") -> bool:
        """Globo de la bandeja. False si no hay bandeja (quien llama usa otro aviso)."""
        tray = self.icono_tray
        if tray is None:
            return False
        icono = self._ICONOS_AVISO.get(str(tipo or "info").lower(), QSystemTrayIcon.MessageIcon.Information)
        try:
            tray.showMessage(str(titulo or "Lune CD")[:63], str(texto or "")[:255], icono, int(ms))
            return True
        except Exception:
            _log.exception("bandeja: showMessage falló")
            return False

    def aplicar_qss(self, qss: str) -> None:
        """Estilo del menú (ui/tema_qss.qss_menu con la paleta del tema)."""
        self._qss = str(qss or "")
        for m in ([self._menu] if self._menu is not None else []) + self._submenus:
            try:
                m.setStyleSheet(self._qss)
            except RuntimeError:
                pass
