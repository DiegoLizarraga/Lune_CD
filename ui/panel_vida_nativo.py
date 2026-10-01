"""
ui/panel_vida_nativo.py — Ajustes de sentarse (corte 7), la comida, Discord y el
arranque con Windows (corte 8) en la interfaz nativa.

La web tiene sus tarjetas (extra/vida.jsx). La nativa (ui/settings_panel.py) incrusta
este panel, igual que PanelOcioNativo: cada apartado espera 300 ms quieto y escribe UNA
vez en config.json (`ui.tema_qt.escribir_claves`), llama él mismo a `recargar_config()`
del controlador de ese apartado y emite `cambiado(str seccion)`.

- SENTARSE (`asiento`): en la barra de tareas al soltarla encima, en ventanas (apagado
  por defecto: al activarlo sale el aviso anticheat de Mate-Engine), ajuste de altura
  (−64..64 px) y «Sentarse en la barra» / «Bajar» con el estado.
- COMIDA (`comida`): la comida con el clic central; «Batido», «Pastel» y «Guardar».
- DISCORD (`discord`): la presencia, el Application ID (17–20 cifras; D1: sin él no
  hace nada), enseñar el modelo VRM y el enlace del botón (https). Muestra qué se
  publica («Discord ve: …», solo los textos fijos) y nunca títulos de ventana ni el chat.
  «RECONECTAR» lo intenta ya y, si no conecta, dice por qué (Discord cerrado, sin
  Application ID, otra Lune ya publica: el `motivo` del controlador).
- ARRANQUE (`arranque`): cómo aparece Lune al arrancar con Windows (bandeja, asistente
  o ventana) y cuánto espera, con el estado de la entrada (desactivada desde el
  Administrador de tareas, carpeta movida…). La casilla «Arrancar Lune junto con
  Windows» sigue en settings_panel.

    panel = PanelVidaNativo(config, asiento=vida.asiento, comida=vida.comida, discord=vida.discord)
    panel.enlazar(servicios_c4)  # si llegan después (la nativa monta al final); se suelta solo al desmontar
    panel.guardar_ya()           # en el «Guardar» de Ajustes

Estilo de ui/theme.py (COLORS), como el resto de la nativa.
"""
from __future__ import annotations

import copy
import logging
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

_log = logging.getLogger("lune.panel_vida")

SECCIONES = ("asiento", "comida", "discord", "arranque")
ESPERA_GUARDADO_MS = 300
OFFSET_MAX = 64
RETRASO_MAX = 120
COMOS = (("bandeja", "En la bandeja (sin ventana)"), ("asistente", "Con la asistente en escritorio"),
         ("ventana", "Con la ventana abierta"))
ID_DISCORD = re.compile(r"^\d{17,20}$")
AVISO_ANTICHEAT = ("Para sentarse en ventanas, Lune lee la posición de las ventanas abiertas (sin tocarlas ni "
                   "leer lo que hay dentro) y solo mueve la suya. Algunos anticheats de juegos online vigilan a "
                   "los programas que miran ventanas: con un juego delante Lune no mira nada, pero si te "
                   "preocupa, déjalo apagado (Mate-Engine avisa igual).")
PRIVACIDAD_DISCORD = ("Discord solo recibe «Lune CD · <modo>» y un estado fijo (bailando, durmiendo, sentada…). "
                      "Nunca títulos de ventanas, programas, el chat, el personaje ni tus alarmas; con un juego "
                      "delante, nada.")


def _escribir(config: Any, cambios: Dict[Tuple[str, str], Any]) -> bool:
    try:
        from ui.tema_qt import escribir_claves
    except Exception:
        escribir_claves = None
    if escribir_claves is not None:
        return bool(escribir_claves(config, cambios))
    try:
        for (s, k), v in cambios.items():
            config.set(s, k, copy.deepcopy(v))
        return True
    except Exception:
        _log.exception("panel vida: no pude guardar")
        return False


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("panel vida: %s.%s falló", type(obj).__name__, metodo)
        return None


def texto_discord_ve(estado: Any) -> str:
    """«Discord ve: Lune CD · Escritorio · 3D — Bailando ♪» (solo textos de la lista fija)."""
    from ui.puente_vida import publicacion_segura
    e = estado if isinstance(estado, dict) else {}
    if not e.get("activo"):
        return "Discord ve: nada (apagado)."
    p = publicacion_segura(e.get("publicando")) or publicacion_segura(e.get("vista_previa"))
    if p is None:
        return "Discord ve: nada ahora mismo (con un juego delante no se publica)."
    return f"Discord ve: {p['details']} — {p['state']}"


def texto_autoinicio(e: Any) -> str:
    e = e if isinstance(e, dict) else {}
    if not e.get("disponible", True):
        return "Solo en Windows."
    if e.get("registrado") and not e.get("aprobado"):
        return ("Desactivado desde el Administrador de tareas (pestaña Inicio). Para volver a activarlo, "
                "marca «Arrancar Lune junto con Windows».")
    if e.get("registrado") and not e.get("ruta_ok"):
        return "La entrada apunta a otra carpeta: se corrige sola la próxima vez que abras Lune."
    if e.get("activo"):
        return "Activado: Lune arranca con Windows."
    return "Desactivado (casilla «Arrancar Lune junto con Windows»)."


class PanelVidaNativo(QWidget):
    """Sentarse, comida, Discord y arranque con Windows para la nativa."""

    cambiado = pyqtSignal(str)

    def __init__(self, config: Any = None, parent: Optional[QWidget] = None, *,
                 asiento: Any = None, comida: Any = None, discord: Any = None,
                 retardo_ms: int = ESPERA_GUARDADO_MS, autoinicio: Any = None):
        super().__init__(parent)
        self.config = config
        self.asiento = asiento
        self.comida = comida
        self.discord = discord
        self._autoinicio = autoinicio
        self._autoinicio_inyectado = autoinicio is not None
        self._enganchados: List[Any] = []
        self._pendientes: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._cargando = False
        self.ultimo_guardado: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._conectados: List[Tuple[Any, Callable]] = []

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(retardo_ms)))
        self._timer.timeout.connect(self.guardar_ya)

        self._construir()
        self.recargar()
        self._conectar_servicios()
        self._pintar_servicios()

    # ── Servicios ────────────────────────────────────────────────────────────────
    def enlazar(self, vida: Any = None, *, asiento: Any = None, comida: Any = None, discord: Any = None) -> None:
        """Los controladores llegan (o cambian) después de construir el panel:
        `enlazar(servicios_vida)` (o un ServiciosCorte4 con `.vida`) o por nombre.
        None los suelta. Se apunta en `_deshacer` de lo que se le da: cuando esos
        servicios se desmontan (cambio de interfaz, salir), los suelta antes de que se
        borren."""
        self._desconectar_servicios()
        if vida is not None:
            base = getattr(vida, "vida", None) or vida
            asiento = getattr(base, "asiento", asiento)
            comida = getattr(base, "comida", comida)
            discord = getattr(base, "discord", discord)
        self.asiento, self.comida, self.discord = asiento, comida, discord
        self._conectar_servicios()
        self._pintar_servicios()
        deshacer = getattr(vida, "_deshacer", None) if vida is not None else None
        if isinstance(deshacer, list) and not any(x is vida for x in self._enganchados):
            self._enganchados.append(vida)
            mios = (asiento, comida, discord)

            def soltar() -> None:
                try:
                    if (self.asiento, self.comida, self.discord) == mios:
                        self.enlazar(None)
                except RuntimeError:                       # el panel ya se borró
                    pass
            deshacer.append(soltar)

    def _conectar_servicios(self) -> None:
        for obj, senal, slot in ((self.asiento, "cambio", self._pintar_asiento),
                                 (self.comida, "cambio", self._pintar_comida),
                                 (self.discord, "estado_cambio", self._pintar_discord)):
            s = getattr(obj, senal, None) if obj is not None else None
            if s is not None and hasattr(s, "connect"):
                try:
                    s.connect(slot)
                    self._conectados.append((s, slot))
                except (TypeError, RuntimeError):
                    pass

    def _desconectar_servicios(self) -> None:
        for s, slot in self._conectados:
            try:
                s.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._conectados = []

    def _pintar_servicios(self) -> None:
        a, c = self.asiento is not None, self.comida is not None
        for w in (self.btn_sentarse, self.btn_bajar):
            w.setVisible(a)
        for w in (self.btn_batido, self.btn_pastel, self.btn_guardar_comida):
            w.setVisible(c)
        self._pintar_asiento()
        self._pintar_comida()
        self._pintar_discord()
        self._pintar_arranque()

    # ── Config ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _defecto(seccion: str, clave: str, respaldo: Any = None) -> Any:
        try:
            from nucleo.config import Config
            return copy.deepcopy(Config.DEFAULT_CONFIG.get(seccion, {}).get(clave, respaldo))
        except Exception:
            return respaldo

    def _leer(self, seccion: str, clave: str, respaldo: Any = None) -> Any:
        defecto = self._defecto(seccion, clave, respaldo)
        cfg = self.config
        if cfg is None:
            return defecto
        try:
            datos = getattr(cfg, "config", None)
            if isinstance(datos, dict):
                v = datos.get(seccion, {}).get(clave, defecto)
            elif isinstance(cfg, dict):
                v = cfg.get(seccion, {}).get(clave, defecto)
            else:
                v = cfg.get(seccion, clave, defecto)
        except Exception:
            v = defecto
        return copy.deepcopy(v)

    def _poner(self, seccion_ui: str, seccion: str, clave: str, valor: Any) -> None:
        if self._cargando:
            return
        self._pendientes.setdefault(seccion_ui, {})[(seccion, clave)] = copy.deepcopy(valor)
        self._timer.start()

    def _quitar_pendiente(self, seccion_ui: str, seccion: str, clave: str) -> None:
        self._pendientes.get(seccion_ui, {}).pop((seccion, clave), None)

    @property
    def pendiente(self) -> bool:
        return any(self._pendientes.values())

    def guardar_ya(self) -> List[str]:
        """Escribe ya lo pendiente (una sola escritura), aplica en caliente
        (`recargar_config` del controlador) y emite `cambiado` por apartado."""
        self._timer.stop()
        pend = {s: c for s, c in self._pendientes.items() if c}
        self._pendientes = {}
        if not pend:
            return []
        todo: Dict[Tuple[str, str], Any] = {}
        for s in SECCIONES:
            todo.update(pend.get(s, {}))
        if not _escribir(self.config, todo):
            self._estado(self.estado_general, "No pude guardar en config.json.", error=True)
            return []
        hechas = [s for s in SECCIONES if s in pend]
        self.ultimo_guardado = {s: dict(pend[s]) for s in hechas}
        ctl = {"asiento": self.asiento, "comida": self.comida, "discord": self.discord, "arranque": None}
        for s in hechas:
            _llamar(ctl[s], "recargar_config")
            self.cambiado.emit(s)
        self._pintar_servicios()
        return hechas

    def hideEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        self.guardar_ya()
        super().hideEvent(ev)

    # ── Estilo ───────────────────────────────────────────────────────────────────
    def _titulo(self, texto: str) -> QLabel:
        t = QLabel(texto)
        t.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        t.setStyleSheet(f"color:{COLORS['accent']};border:none;letter-spacing:1px;padding-top:6px;")
        return t

    def _caja(self, nombre: str) -> Tuple[QFrame, QVBoxLayout]:
        caja = QFrame()
        caja.setObjectName(nombre)
        caja.setStyleSheet(f"QFrame#{nombre}{{background:{COLORS['surface']};border:1px solid {COLORS['border']};"
                           f"border-radius:3px;}}")
        fl = QVBoxLayout(caja)
        fl.setContentsMargins(14, 14, 14, 14)
        fl.setSpacing(8)
        return caja, fl

    def _texto(self, texto: str, tenue: bool = False) -> QLabel:
        lbl = QLabel(texto)
        lbl.setTextFormat(Qt.TextFormat.PlainText)          # nada de HTML de fuera (usuario de Discord…)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{COLORS['text_muted' if tenue else 'text']};border:none;background:transparent;")
        return lbl

    def _check(self, texto: str, ayuda: str = "") -> QCheckBox:
        c = QCheckBox(texto)
        c.setCursor(Qt.CursorShape.PointingHandCursor)
        if ayuda:
            c.setToolTip(ayuda)
        c.setStyleSheet(
            f"QCheckBox{{color:{COLORS['text']};spacing:8px;background:transparent;border:none;}}"
            f"QCheckBox::indicator{{width:14px;height:14px;border:1px solid {COLORS['border2']};"
            f"background:{COLORS['surface2']};border-radius:2px;}}"
            f"QCheckBox::indicator:checked{{background:{COLORS['accent']};border-color:{COLORS['cyan_dark']};}}")
        return c

    def _combo(self) -> QComboBox:
        c = QComboBox()
        c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        c.setStyleSheet(
            f"QComboBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
            f"border-radius:3px;padding:6px 10px;color:{COLORS['text']};}}"
            f"QComboBox QAbstractItemView{{background:{COLORS['surface2']};color:{COLORS['text']};"
            f"selection-background-color:{COLORS['accent']};selection-color:{COLORS['bg']};}}")
        return c

    def _spin(self, minimo: int, maximo: int, sufijo: str = "") -> QSpinBox:
        s = QSpinBox()
        s.setRange(minimo, maximo)
        if sufijo:
            s.setSuffix(sufijo)
        s.setFixedWidth(96)
        s.setStyleSheet(f"QSpinBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
                        f"border-radius:3px;padding:4px 6px;color:{COLORS['text']};}}")
        return s

    def _linea(self, placeholder: str = "", maximo: int = 64) -> QLineEdit:
        e = QLineEdit()
        e.setMaxLength(maximo)
        e.setPlaceholderText(placeholder)
        e.setStyleSheet(f"QLineEdit{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
                        f"border-radius:3px;padding:6px 10px;color:{COLORS['text']};}}"
                        f"QLineEdit:focus{{border-color:{COLORS['accent']};}}")
        return e

    def _boton(self, texto: str, principal: bool = False) -> QPushButton:
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(FONT_DISPLAY, 9, QFont.Weight.Bold))
        b.setFixedHeight(30)
        borde = COLORS["cyan_dark"] if principal else COLORS["border"]
        color = COLORS["accent"] if principal else COLORS["text_muted"]
        b.setStyleSheet(
            f"QPushButton{{background:{COLORS['surface2']};color:{color};border:2px solid {borde};"
            f"border-radius:3px;padding:0 12px;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:{COLORS['surface3']};color:{COLORS['accent']};border-color:{COLORS['accent']};}}"
            f"QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        return b

    def _fila(self, etiqueta_: str, widget: QWidget, extra: Optional[QWidget] = None) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(10)
        lbl = QLabel(etiqueta_)
        lbl.setMinimumWidth(190)
        lbl.setStyleSheet(f"color:{COLORS['text']};border:none;background:transparent;")
        fila.addWidget(lbl)
        ancho = isinstance(widget, (QComboBox, QLineEdit))
        fila.addWidget(widget, 1 if ancho else 0)
        if extra is not None:
            fila.addWidget(extra)
        if not ancho:
            fila.addStretch(1)
        return fila

    @staticmethod
    def _estado(lbl: QLabel, texto: str, error: bool = False, aviso: bool = False) -> None:
        lbl.setText(texto)
        color = COLORS["error"] if error else (COLORS["warning"] if aviso else COLORS["text_muted"])
        lbl.setStyleSheet(f"color:{color};border:none;background:transparent;")

    def _botones(self, fl: QVBoxLayout, *botones: QPushButton) -> None:
        fila = QHBoxLayout()
        fila.setSpacing(8)
        for b in botones:
            fila.addWidget(b)
        fila.addStretch(1)
        fl.addLayout(fila)

    # ── Construcción ─────────────────────────────────────────────────────────────
    def _construir(self) -> None:
        self.setObjectName("vidaPanel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)
        self._construir_asiento(raiz)
        self._construir_comida(raiz)
        self._construir_discord(raiz)
        self._construir_arranque(raiz)
        self.estado_general = self._texto("", tenue=True)
        raiz.addWidget(self.estado_general)

    def _construir_asiento(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("SENTARSE"))
        caja, fl = self._caja("asientoCaja")
        self.chk_barra = self._check("Sentarse en la barra de tareas al soltarla encima",
                                     "Arrástrala hasta la barra de abajo y suéltala: se sienta con las piernas colgando.")
        self.chk_barra.toggled.connect(lambda v: self._poner("asiento", "avatar", "sentarse_barra", bool(v)))
        self.chk_ventanas = self._check("Sentarse en ventanas",
                                        "Arrástrala medio segundo sobre el borde de arriba de una ventana.")
        self.chk_ventanas.toggled.connect(self._al_ventanas)
        fl.addWidget(self.chk_barra)
        fl.addWidget(self.chk_ventanas)
        self.aviso_anticheat = self._texto(AVISO_ANTICHEAT)
        self._estado(self.aviso_anticheat, AVISO_ANTICHEAT, aviso=True)
        self.aviso_anticheat.setVisible(False)
        fl.addWidget(self.aviso_anticheat)
        self.spin_offset = self._spin(-OFFSET_MAX, OFFSET_MAX, " px")
        self.spin_offset.setToolTip("Sube (negativo) o baja (positivo) dónde se apoya, si queda flotando o hundida.")
        self.spin_offset.valueChanged.connect(lambda v: self._poner("asiento", "avatar", "sentarse_offset_px", int(v)))
        fl.addLayout(self._fila("Ajuste de altura del asiento", self.spin_offset))
        self.btn_sentarse = self._boton("SENTARSE EN LA BARRA", principal=True)
        self.btn_sentarse.clicked.connect(self.sentarse)
        self.btn_bajar = self._boton("BAJAR")
        self.btn_bajar.clicked.connect(self.bajar)
        self._botones(fl, self.btn_sentarse, self.btn_bajar)
        self.estado_asiento = self._texto("", tenue=True)
        fl.addWidget(self.estado_asiento)
        raiz.addWidget(caja)

    def _construir_comida(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("COMIDA"))
        caja, fl = self._caja("comidaCaja")
        self.chk_comida = self._check("Comida con el clic central (batido y pastel)",
                                      "Clic central sobre Lune → menú con Batido y Pastel. La comida sigue al "
                                      "ratón; pásala rápido por su cabeza para dársela. Se guarda sola a los 2 min.")
        self.chk_comida.toggled.connect(lambda v: self._poner("comida", "comida", "activa", bool(v)))
        fl.addWidget(self.chk_comida)
        self.btn_batido = self._boton("BATIDO", principal=True)
        self.btn_batido.clicked.connect(lambda: self.comer("batido"))
        self.btn_pastel = self._boton("PASTEL", principal=True)
        self.btn_pastel.clicked.connect(lambda: self.comer("pastel"))
        self.btn_guardar_comida = self._boton("GUARDAR")
        self.btn_guardar_comida.clicked.connect(self.guardar_comida)
        self._botones(fl, self.btn_batido, self.btn_pastel, self.btn_guardar_comida)
        self.estado_comida = self._texto("", tenue=True)
        fl.addWidget(self.estado_comida)
        raiz.addWidget(caja)

    def _construir_discord(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("DISCORD"))
        caja, fl = self._caja("discordCaja")
        self.chk_discord = self._check("Enseñar en Discord lo que hace Lune (Rich Presence)")
        self.chk_discord.toggled.connect(lambda v: self._poner("discord", "discord", "activo", bool(v)))
        fl.addWidget(self.chk_discord)
        self.linea_id = self._linea("123456789012345678", 20)
        self.linea_id.setToolTip("discord.com/developers → tu aplicación → Application ID. No es un secreto.")
        self.linea_id.textChanged.connect(self._al_client_id)
        fl.addLayout(self._fila("Application ID", self.linea_id))
        self.chk_modelo = self._check("Enseñar el nombre del modelo 3D")
        self.chk_modelo.toggled.connect(lambda v: self._poner("discord", "discord", "mostrar_modelo", bool(v)))
        fl.addWidget(self.chk_modelo)
        self.linea_url = self._linea("https://…", 512)
        self.linea_url.setToolTip("Botón «Conoce a Lune» (opcional; solo lo ven los demás).")
        self.linea_url.textChanged.connect(self._al_url)
        fl.addLayout(self._fila("Enlace del botón", self.linea_url))
        self.error_discord = self._texto("", tenue=True)
        fl.addWidget(self.error_discord)
        fl.addWidget(self._texto(PRIVACIDAD_DISCORD, tenue=True))
        self.discord_ve = self._texto("", tenue=True)
        self.discord_ve.setFont(QFont(FONT_MONO, 9))
        fl.addWidget(self.discord_ve)
        # «Reconectar»: lo intenta ya y, si no puede, dice por qué (Discord cerrado, sin ID…).
        self.btn_reconectar = self._boton("RECONECTAR")
        self.btn_reconectar.setToolTip("Vuelve a intentar conectar con Discord ahora mismo.")
        self.btn_reconectar.clicked.connect(self.reconectar_discord)
        self._botones(fl, self.btn_reconectar)
        self.estado_discord = self._texto("", tenue=True)
        fl.addWidget(self.estado_discord)
        raiz.addWidget(caja)

    def _construir_arranque(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("ARRANQUE CON WINDOWS"))
        caja, fl = self._caja("arranqueCaja")
        self.combo_como = self._combo()
        for clave, texto in COMOS:
            self.combo_como.addItem(texto, clave)
        self.combo_como.currentIndexChanged.connect(
            lambda *_: self._poner("arranque", "sistema", "autoinicio_como", self.combo_como.currentData()))
        fl.addLayout(self._fila("Al arrancar con Windows", self.combo_como))
        self.spin_espera = self._spin(0, RETRASO_MAX, " s")
        self.spin_espera.setToolTip("Espera antes de cargar la interfaz: el inicio de sesión va más ligero.")
        self.spin_espera.valueChanged.connect(
            lambda v: self._poner("arranque", "sistema", "autoinicio_retraso_s", int(v)))
        fl.addLayout(self._fila("Esperar antes de abrir", self.spin_espera))
        fl.addWidget(self._texto("Sin pantalla de inicio. En modo terminal, la consola se abre minimizada.", tenue=True))
        self.estado_arranque = self._texto("", tenue=True)
        fl.addWidget(self.estado_arranque)
        raiz.addWidget(caja)

    # ── Recarga ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _entero(v: Any, defecto: int) -> int:
        if isinstance(v, bool):
            return defecto
        try:
            return int(float(v))
        except (TypeError, ValueError, OverflowError):
            return defecto

    def recargar(self) -> None:
        """Vuelve a leer config.json en los controles (sin guardar nada)."""
        self._cargando = True
        try:
            self.chk_barra.setChecked(self._leer("avatar", "sentarse_barra", True) is not False)
            self.chk_ventanas.setChecked(self._leer("avatar", "sentarse_ventanas", False) is True)
            off = self._entero(self._leer("avatar", "sentarse_offset_px", 0), 0)
            self.spin_offset.setValue(max(-OFFSET_MAX, min(OFFSET_MAX, off)))
            self.aviso_anticheat.setVisible(False)

            self.chk_comida.setChecked(self._leer("comida", "activa", True) is not False)

            self.chk_discord.setChecked(self._leer("discord", "activo", False) is True)
            cid = str(self._leer("discord", "client_id", "") or "").strip()
            self.linea_id.setText(cid if ID_DISCORD.match(cid) else "")
            self.chk_modelo.setChecked(self._leer("discord", "mostrar_modelo", False) is True)
            url = self._leer("discord", "boton_url", "")
            self.linea_url.setText(url if isinstance(url, str) and self._url_ok(url) else "")
            self._estado(self.error_discord, "")

            como = self._leer("sistema", "autoinicio_como", "bandeja")
            i = self.combo_como.findData(como if como in dict(COMOS) else "bandeja")
            self.combo_como.setCurrentIndex(max(0, i))
            espera = self._entero(self._leer("sistema", "autoinicio_retraso_s", 20), 20)
            self.spin_espera.setValue(max(0, min(RETRASO_MAX, espera)))
        finally:
            self._cargando = False
        self._pintar_arranque()

    # ── Cambios con validación ───────────────────────────────────────────────────
    def _al_ventanas(self, v: bool) -> None:
        # Al ENCENDERLO a mano sale el aviso anticheat (como Mate-Engine); cargar no avisa.
        self.aviso_anticheat.setVisible(bool(v) and not self._cargando)
        self._poner("asiento", "avatar", "sentarse_ventanas", bool(v))

    @staticmethod
    def _url_ok(url: str) -> bool:
        from ui.puente_vida import url_boton_valida
        return url_boton_valida(url)

    def _al_client_id(self, texto: str) -> None:
        t = str(texto or "").strip()
        if t and not ID_DISCORD.match(t):
            self._quitar_pendiente("discord", "discord", "client_id")
            self._estado(self.error_discord, "El Application ID son de 17 a 20 cifras.", error=True)
            return
        self._estado(self.error_discord, "")
        self._poner("discord", "discord", "client_id", t)

    def _al_url(self, texto: str) -> None:
        t = str(texto or "").strip()
        if t and not self._url_ok(t):
            self._quitar_pendiente("discord", "discord", "boton_url")
            self._estado(self.error_discord, "El enlace del botón tiene que empezar por https://.", error=True)
            return
        self._estado(self.error_discord, "")
        self._poner("discord", "discord", "boton_url", t)

    # ── Botones ──────────────────────────────────────────────────────────────────
    def sentarse(self) -> bool:
        r = _llamar(self.asiento, "sentar", "barra")
        ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (False, ""))
        self._pintar_asiento()
        if texto:
            self._estado(self.estado_asiento, str(texto), error=not ok)
        return bool(ok)

    def bajar(self) -> bool:
        r = _llamar(self.asiento, "bajar") is True
        self._pintar_asiento()
        return r

    def comer(self, id_: str) -> str:
        r = _llamar(self.comida, "alternar", id_)
        self._pintar_comida()
        if not r and self.comida is not None:
            motivo = str(getattr(self.comida, "ultimo_motivo", "") or "")
            texto = "La comida está desactivada." if motivo == "desactivada" else "Ahora no puedo comer."
            self._estado(self.estado_comida, texto, error=True)
        return str(r or "")

    def guardar_comida(self) -> bool:
        r = _llamar(self.comida, "guardar") is True
        self._pintar_comida()
        return r

    def reconectar_discord(self) -> bool:
        """«Reconectar»: guarda lo pendiente de Discord (un ID recién escrito) y lo intenta ya.
        Si no se puede ni intentar, el motivo; lo demás llega por estado_cambio."""
        if self.discord is None:
            self._estado(self.estado_discord, "Me conecto con la app abierta (y Discord abierto).", aviso=True)
            return False
        if self._pendientes.get("discord"):
            self.guardar_ya()
        r = _llamar(self.discord, "reconectar")
        r = r if isinstance(r, dict) else {"ok": False, "motivo": "No pude volver a intentarlo; prueba otra vez."}
        if r.get("ok"):
            self._estado(self.estado_discord, str(r.get("texto") or "Lo intento ahora…"))
        else:
            self._estado(self.estado_discord, str(r.get("motivo") or "No pude reconectar."), error=True)
        return bool(r.get("ok"))

    # ── Estado a la vista ────────────────────────────────────────────────────────
    def _pintar_asiento(self, *_: Any) -> None:
        a = self.asiento
        if a is None:
            self._estado(self.estado_asiento, "Se sienta la asistente en escritorio: sácala para probarlo.")
            return
        e = _llamar(a, "estado")
        e = e if isinstance(e, dict) else {}
        sentada = e.get("sentada") if e.get("sentada") in ("barra", "ventana") else ""
        self.btn_sentarse.setVisible(not sentada)
        self.btn_bajar.setVisible(bool(sentada))
        if sentada:
            texto = "Sentada en la barra de tareas." if sentada == "barra" else "Sentada en una ventana."
        elif e.get("juego"):
            texto = "Con un juego delante no se sienta (ni mira las ventanas)."
        elif not e.get("disponible"):
            texto = "De pie. Saca a la asistente al escritorio para sentarla."
        else:
            texto = "De pie."
        self._estado(self.estado_asiento, texto)

    def _pintar_comida(self, *_: Any) -> None:
        c = self.comida
        if c is None:
            self._estado(self.estado_comida, "La comida sale con la app abierta (clic central sobre Lune).")
            return
        e = _llamar(c, "estado")
        e = e if isinstance(e, dict) else {}
        self.btn_guardar_comida.setEnabled(bool(e.get("activa")))
        if e.get("activa"):
            try:
                from nucleo import comida as nc
                v = nc.variante_de(e.get("id"), e.get("variante"))
                com = nc.comida(e.get("id"))
                que = f"{com.nombre.lower()} de {v.nombre}" if com and v else "comida"
            except Exception:
                que = "comida"
            self._estado(self.estado_comida, f"En la mano: {que}. Pásala rápido por su cabeza.")
        else:
            self._estado(self.estado_comida, "" if e.get("disponible", True) else "Desactivada.")

    def _pintar_discord(self, *_: Any) -> None:
        d = self.discord
        e = _llamar(d, "estado") if d is not None else None
        e = e if isinstance(e, dict) else {"activo": self._leer("discord", "activo", False) is True}
        self.discord_ve.setText(texto_discord_ve(e))
        if d is None:
            texto = "Se conecta con la app abierta (y Discord abierto)."
        elif not e.get("activo"):
            texto = "Apagado."
        elif e.get("sin_id") or not str(self._leer("discord", "client_id", "") or "").strip():
            texto = "Falta el Application ID: crea una app en discord.com/developers y pega aquí su ID."
        elif e.get("conectado"):
            usuario = re.sub(r"[\x00-\x1f\x7f]", "", str(e.get("usuario") or ""))[:40]
            texto = f"Conectado{f' como {usuario}' if usuario else ''}."
        else:
            # El motivo con el siguiente paso (Discord cerrado, otra Lune ya publica…).
            motivo = re.sub(r"[\x00-\x1f\x7f]", "", str(e.get("motivo") or ""))[:200]
            err = re.sub(r"[\x00-\x1f\x7f]", "", str(e.get("error") or ""))[:160]
            texto = motivo or f"Sin conectar{f': {err}' if err else ' (esperando a Discord)'}."
        self._estado(self.estado_discord, texto)

    def _mod_autoinicio(self) -> Any:
        if self._autoinicio is None:
            try:
                from servicios import autoinicio
                self._autoinicio = autoinicio
            except Exception:
                return None
        return self._autoinicio

    def estado_arranque_dict(self) -> Dict[str, Any]:
        mod = self._mod_autoinicio()
        modo = str(self._leer("interfaz", "modo", "web") or "web")
        e = _llamar(mod, "estado", modo) if mod is not None else None
        e = dict(e) if isinstance(e, dict) else {}
        e["disponible"] = mod is not None and (self._autoinicio_inyectado or sys.platform == "win32")
        return e

    def _pintar_arranque(self, *_: Any) -> None:
        self._estado(self.estado_arranque, texto_autoinicio(self.estado_arranque_dict()))


__all__ = ("PanelVidaNativo", "SECCIONES", "AVISO_ANTICHEAT", "PRIVACIDAD_DISCORD", "texto_discord_ve",
           "texto_autoinicio")
