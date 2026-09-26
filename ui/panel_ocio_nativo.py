"""
ui/panel_ocio_nativo.py — Ajustes de alarmas, pantalla grande/salvapantallas y
baile en la interfaz nativa (cortes 5 y 6).

La web tiene sus tarjetas (extra/alarmas.jsx y extra/baile.jsx). La nativa
(ui/settings_panel.py) incrusta este panel, con tres apartados que guardan al
momento como PanelEscritorioNativo: esperan 300 ms quietos y escriben UNA vez en
config.json (`ui.tema_qt.escribir_claves`: `config.config[...]` + `config.save()`).

- ALARMAS (`alarmas`): activas, pantalla grande al sonar, decir el texto, segundos
  de bloqueo, minutos de posponer y de recuperación, volumen y sonido. Botones
  «Editar alarmas…» (DialogoAlarmas de ControlAlarmasQt), «Probar» y
  «Temporizador 5 min»; resumen de lo programado.
- PANTALLA GRANDE (`grande`): salvapantallas activo, tiempo de espera (los 11
  pasos de Mate-Engine), «un clic sale también de la pantalla grande», fondo
  oscuro y reloj; «Probar salvapantallas» y «Pantalla grande» (alternar), con el
  atajo configurado a la vista.
- BAILE (`baile`): bailar sola con la música, umbral, apps permitidas (con «De
  las que suenan…»), cambiar de baile cada N s y partículas; «Bailar / Parar».

Tras escribir un apartado emite `cambiado(str seccion)` y llama él mismo a
`recargar_config()` del controlador de ese apartado (si lo tiene): quien lo
integra no tiene que aplicar nada más.

    panel = PanelOcioNativo(config, alarmas=ocio.alarmas, grande=ocio.grande, baile=ocio.baile)
    panel.enlazar(ocio)          # si los servicios llegan después (la nativa monta al final)
    panel.guardar_ya()           # en el «Guardar» de Ajustes

Estilo de ui/theme.py (COLORS), como el resto de la nativa.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu,
    QPushButton, QSizePolicy, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from nucleo import pantalla_grande as pg
from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

_log = logging.getLogger("lune.panel_ocio")

SECCIONES = ("alarmas", "grande", "baile")
ESPERA_GUARDADO_MS = 300
MAX_APPS = 60
UMBRAL_MIN, UMBRAL_MAX = 0.02, 0.60
CAMBIAR_MIN, CAMBIAR_MAX = 5, 120
ETIQUETAS_SONIDO = {"azar": "Al azar", "alarma_1": "Alarma 1", "alarma_2": "Alarma 2", "alarma_3": "Alarma 3"}
_APP = re.compile(r"[\w .\-()+&']{1,60}")


def sonidos() -> List[str]:
    """«azar» y los WAV de alarma (servicios.alarmas_aviso.SONIDOS si existe)."""
    try:
        from servicios.alarmas_aviso import SONIDOS
        lista = [str(s) for s in SONIDOS]
    except Exception:
        lista = ["alarma_1", "alarma_2", "alarma_3"]
    return ["azar", *[s for s in lista if s != "azar"]]


def normalizar_app(nombre: Any) -> Optional[str]:
    """«C:\\…\\Spotify.exe» → «Spotify»; None si no vale. Usa la regla del detector
    de música (servicios.musica_detector.normalizar_nombre_app) si está."""
    try:
        from servicios.musica_detector import normalizar_nombre_app as oficial
    except Exception:
        oficial = None
    if oficial is not None:
        try:
            return oficial(nombre)
        except Exception:
            return None
    if not isinstance(nombre, str):
        return None
    n = re.split(r"[\\/]", nombre.strip().strip('"\'').strip())[-1].strip()
    if n.lower().endswith(".exe"):
        n = n[:-4].strip()
    return n if n and _APP.fullmatch(n) else None


def texto_atajo(config: Any, id_: str) -> str:
    """El combo guardado para la acción `id_` bonito («Ctrl+Alt+Shift+B») o ""."""
    try:
        lista = config.get("atajos", "lista", []) if not isinstance(config, dict) else \
            config.get("atajos", {}).get("lista", [])
    except Exception:
        lista = []
    for e in lista or ():
        if isinstance(e, dict) and e.get("id") == id_ and e.get("combo"):
            combo = str(e["combo"])
            try:
                from servicios.atajos_globales import parsear_combo, texto_combo
                return texto_combo(*parsear_combo(combo))
            except Exception:
                return "+".join(p.capitalize() for p in combo.split("+"))
    return ""


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
        _log.exception("panel ocio: no pude guardar")
        return False


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("panel ocio: %s.%s falló", type(obj).__name__, metodo)
        return None


class PanelOcioNativo(QWidget):
    """Alarmas, pantalla grande y salvapantallas, y baile para la nativa."""

    cambiado = pyqtSignal(str)

    def __init__(self, config: Any = None, parent: Optional[QWidget] = None, *,
                 alarmas: Any = None, grande: Any = None, baile: Any = None,
                 retardo_ms: int = ESPERA_GUARDADO_MS):
        super().__init__(parent)
        self.config = config
        self.alarmas = alarmas
        self.grande = grande
        self.baile = baile
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
    def enlazar(self, ocio: Any = None, *, alarmas: Any = None, grande: Any = None, baile: Any = None) -> None:
        """Los controladores llegan (o cambian) después de construir el panel:
        `enlazar(servicios_ocio)` o por nombre. None los suelta."""
        self._desconectar_servicios()
        if ocio is not None:
            alarmas = getattr(ocio, "alarmas", alarmas)
            grande = getattr(ocio, "grande", grande)
            baile = getattr(ocio, "baile", baile)
        self.alarmas, self.grande, self.baile = alarmas, grande, baile
        self._conectar_servicios()
        self._pintar_servicios()

    def _conectar_servicios(self) -> None:
        for obj, senal, slot in ((self.alarmas, "cambio", self._pintar_resumen_alarmas),
                                 (self.grande, "cambio", self._pintar_estado_grande),
                                 (self.baile, "estado_cambio", self._pintar_estado_baile)):
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
        a, g, b = self.alarmas is not None, self.grande is not None, self.baile is not None
        for w in (self.btn_editar_alarmas, self.btn_probar_alarma, self.btn_temporizador):
            w.setVisible(a)
        for w in (self.btn_probar_salva, self.btn_grande):
            w.setVisible(g)
        self.btn_bailar.setVisible(b)
        self.btn_suenan.setVisible(b and callable(getattr(self.baile, "apps_sonando", None)))
        self._pintar_resumen_alarmas()
        self._pintar_estado_grande()
        self._pintar_estado_baile()

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
        ctl = {"alarmas": self.alarmas, "grande": self.grande, "baile": self.baile}
        for s in hechas:
            _llamar(ctl[s], "recargar_config")
            self.cambiado.emit(s)
        self._pintar_estado_grande()
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
        # Texto plano: el resumen lleva textos de alarmas (alarmas.json, el chat, el modelo)
        # que un QLabel en automático interpretaría como HTML (revisión 4-5-6, SM1).
        lbl.setTextFormat(Qt.TextFormat.PlainText)
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

    def _slider(self, minimo: int, maximo: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(minimo, maximo)
        s.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px;background:{COLORS['surface3']};border-radius:2px;}}"
            f"QSlider::sub-page:horizontal{{background:{COLORS['accent']};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{COLORS['text']};border:2px solid {COLORS['accent']};"
            f"width:10px;margin:-6px 0;border-radius:2px;}}")
        return s

    def _linea(self) -> QLineEdit:
        e = QLineEdit()
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
        ancho = isinstance(widget, (QSlider, QComboBox, QLineEdit))
        fila.addWidget(widget, 1 if ancho else 0)
        if extra is not None:
            fila.addWidget(extra)
        if not ancho:
            fila.addStretch(1)
        return fila

    @staticmethod
    def _estado(lbl: QLabel, texto: str, error: bool = False) -> None:
        lbl.setText(texto)
        color = COLORS["error"] if error else COLORS["text_muted"]
        lbl.setStyleSheet(f"color:{color};border:none;background:transparent;")

    # ── Construcción ─────────────────────────────────────────────────────────────
    def _construir(self) -> None:
        self.setObjectName("ocioPanel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)
        self._construir_alarmas(raiz)
        self._construir_grande(raiz)
        self._construir_baile(raiz)
        self.estado_general = self._texto("", tenue=True)
        raiz.addWidget(self.estado_general)

    def _construir_alarmas(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("ALARMAS Y TEMPORIZADORES"))
        caja, fl = self._caja("alarmasCaja")
        self.chk_alarmas = self._check("Alarmas activas", "Apagadas, no suena nada (ni se recupera "
                                       "lo que pase mientras).")
        self.chk_alarmas.toggled.connect(lambda v: self._poner("alarmas", "alarmas", "activo", bool(v)))
        self.chk_alarmas_grande = self._check("Al sonar, Lune se pone en pantalla grande",
                                              "Con un juego delante solo suena y avisa.")
        self.chk_alarmas_grande.toggled.connect(
            lambda v: self._poner("alarmas", "alarmas", "pantalla_grande", bool(v)))
        self.chk_decir = self._check("Decir el texto en voz alta al apagarla")
        self.chk_decir.toggled.connect(lambda v: self._poner("alarmas", "alarmas", "decir_texto", bool(v)))
        for c in (self.chk_alarmas, self.chk_alarmas_grande, self.chk_decir):
            fl.addWidget(c)
        self.spin_bloqueo = self._spin(0, 30, " s")
        self.spin_bloqueo.setToolTip("Segundos en los que un clic o una tecla no apagan la alarma recién sonada.")
        self.spin_bloqueo.valueChanged.connect(lambda v: self._poner("alarmas", "alarmas", "bloqueo_s", int(v)))
        fl.addLayout(self._fila("No se apaga sin querer durante", self.spin_bloqueo))
        self.spin_posponer = self._spin(1, 60, " min")
        self.spin_posponer.valueChanged.connect(lambda v: self._poner("alarmas", "alarmas", "posponer_min", int(v)))
        fl.addLayout(self._fila("Posponer", self.spin_posponer))
        self.spin_recuperar = self._spin(0, 120, " min")
        self.spin_recuperar.setToolTip("Si el PC estuvo apagado o suspendido, las alarmas perdidas hace "
                                       "menos de esto suenan al volver; las más viejas solo se avisan.")
        self.spin_recuperar.valueChanged.connect(
            lambda v: self._poner("alarmas", "alarmas", "recuperar_min", int(v)))
        fl.addLayout(self._fila("Recuperar las perdidas de hace", self.spin_recuperar))
        self.slider_volumen = self._slider(0, 100)
        self.valor_volumen = self._texto("80 %", tenue=True)
        self.valor_volumen.setFixedWidth(46)
        self.slider_volumen.valueChanged.connect(self._al_volumen)
        fl.addLayout(self._fila("Volumen", self.slider_volumen, self.valor_volumen))
        self.combo_sonido = self._combo()
        for s in sonidos():
            self.combo_sonido.addItem(ETIQUETAS_SONIDO.get(s, s), s)
        self.combo_sonido.currentIndexChanged.connect(
            lambda *_: self._poner("alarmas", "alarmas", "sonido", self.combo_sonido.currentData()))
        fl.addLayout(self._fila("Sonido", self.combo_sonido))
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.btn_editar_alarmas = self._boton("EDITAR ALARMAS…", principal=True)
        self.btn_editar_alarmas.clicked.connect(self.editar_alarmas)
        self.btn_probar_alarma = self._boton("PROBAR")
        self.btn_probar_alarma.clicked.connect(self.probar_alarma)
        self.btn_temporizador = self._boton("TEMPORIZADOR 5 MIN")
        self.btn_temporizador.clicked.connect(self.temporizador_rapido)
        for b in (self.btn_editar_alarmas, self.btn_probar_alarma, self.btn_temporizador):
            fila.addWidget(b)
        fila.addStretch(1)
        fl.addLayout(fila)
        self.resumen_alarmas = self._texto("", tenue=True)
        fl.addWidget(self.resumen_alarmas)
        raiz.addWidget(caja)

    def _construir_grande(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("PANTALLA GRANDE Y SALVAPANTALLAS"))
        caja, fl = self._caja("grandeCaja")
        self.chk_salva = self._check("Salvapantallas: Lune ocupa la pantalla tras un rato sin tocar el PC",
                                     "No salta con un juego, un vídeo que pide la pantalla, una alarma, "
                                     "ni si está hablando, pensando o bailando.")
        self.chk_salva.toggled.connect(lambda v: self._poner("grande", "salvapantallas", "activo", bool(v)))
        fl.addWidget(self.chk_salva)
        self.slider_paso = self._slider(0, pg.PASO_MAX)
        self.slider_paso.setPageStep(1)
        self.valor_paso = self._texto(pg.etiqueta(0), tenue=True)
        self.valor_paso.setFixedWidth(84)
        self.slider_paso.valueChanged.connect(self._al_paso)
        fl.addLayout(self._fila("Esperar", self.slider_paso, self.valor_paso))
        self.chk_clic_todo = self._check("Un clic sale también de la pantalla grande",
                                         "Si no, el clic la despierta y se queda en pantalla grande.")
        self.chk_clic_todo.toggled.connect(
            lambda v: self._poner("grande", "salvapantallas", "clic_sale_de_todo", bool(v)))
        self.chk_fondo = self._check("Oscurecer el escritorio detrás de Lune")
        self.chk_fondo.toggled.connect(lambda v: self._poner("grande", "salvapantallas", "fondo_oscuro", bool(v)))
        self.chk_reloj = self._check("Enseñar la hora")
        self.chk_reloj.toggled.connect(lambda v: self._poner("grande", "salvapantallas", "reloj", bool(v)))
        for c in (self.chk_clic_todo, self.chk_fondo, self.chk_reloj):
            fl.addWidget(c)
        fl.addWidget(self._texto("Mover el ratón no la despierta: un clic, una tecla o el mando.", tenue=True))
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.btn_probar_salva = self._boton("PROBAR SALVAPANTALLAS")
        self.btn_probar_salva.clicked.connect(self.probar_salvapantallas)
        self.btn_grande = self._boton("PANTALLA GRANDE", principal=True)
        self.btn_grande.clicked.connect(self.alternar_grande)
        fila.addWidget(self.btn_probar_salva)
        fila.addWidget(self.btn_grande)
        fila.addStretch(1)
        fl.addLayout(fila)
        self.estado_grande = self._texto("", tenue=True)
        fl.addWidget(self.estado_grande)
        raiz.addWidget(caja)

    def _construir_baile(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("BAILE CON LA MÚSICA"))
        caja, fl = self._caja("baileCaja")
        self.chk_baile_auto = self._check("Bailar sola cuando suena música en una app permitida",
                                          "Solo mide el volumen de cada app (no graba audio). "
                                          "Con un juego delante no mira nada.")
        self.chk_baile_auto.toggled.connect(lambda v: self._poner("baile", "baile", "auto", bool(v)))
        fl.addWidget(self.chk_baile_auto)
        self.slider_umbral = self._slider(int(UMBRAL_MIN * 100), int(UMBRAL_MAX * 100))
        self.valor_umbral = self._texto("0.05", tenue=True)
        self.valor_umbral.setFixedWidth(46)
        self.slider_umbral.valueChanged.connect(self._al_umbral)
        fl.addLayout(self._fila("Volumen mínimo para contar", self.slider_umbral, self.valor_umbral))
        fl.addWidget(self._texto("Apps que cuentan como música:", tenue=True))
        self.lista_apps = QListWidget()
        self.lista_apps.setFixedHeight(90)
        self.lista_apps.setStyleSheet(f"QListWidget{{background:{COLORS['surface2']};border:1px solid "
                                      f"{COLORS['border']};color:{COLORS['text']};}}"
                                      f"QListWidget::item:selected{{background:{COLORS['surface3']};"
                                      f"color:{COLORS['accent']};}}")
        fl.addWidget(self.lista_apps)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.entrada_app = self._linea()
        self.entrada_app.setPlaceholderText("Spotify")
        self.entrada_app.returnPressed.connect(self._anadir_app_escrita)
        self.btn_app_anadir = self._boton("AÑADIR", principal=True)
        self.btn_app_anadir.clicked.connect(self._anadir_app_escrita)
        self.btn_app_quitar = self._boton("QUITAR")
        self.btn_app_quitar.clicked.connect(self.quitar_app)
        self.btn_suenan = self._boton("DE LAS QUE SUENAN…")
        self.btn_suenan.setToolTip("Elegir entre las apps que están sonando ahora.")
        self.btn_suenan.clicked.connect(self._menu_suenan)
        for w in (self.btn_app_anadir, self.btn_app_quitar, self.btn_suenan):
            fila.addWidget(w)
        fila.insertWidget(0, self.entrada_app, 1)
        fl.addLayout(fila)
        self.chk_cambiar = self._check("Cambiar de baile cada cierto tiempo")
        self.chk_cambiar.toggled.connect(lambda v: self._poner("baile", "baile", "cambiar", bool(v)))
        fl.addWidget(self.chk_cambiar)
        self.spin_cambiar = self._spin(CAMBIAR_MIN, CAMBIAR_MAX, " s")
        self.spin_cambiar.valueChanged.connect(lambda v: self._poner("baile", "baile", "cambiar_s", int(v)))
        fl.addLayout(self._fila("Cada", self.spin_cambiar))
        self.chk_particulas = self._check("Notas musicales mientras baila")
        self.chk_particulas.toggled.connect(lambda v: self._poner("baile", "baile", "particulas", bool(v)))
        fl.addWidget(self.chk_particulas)
        fila2 = QHBoxLayout()
        self.btn_bailar = self._boton("BAILAR", principal=True)
        self.btn_bailar.clicked.connect(self.alternar_baile)
        fila2.addWidget(self.btn_bailar)
        fila2.addStretch(1)
        fl.addLayout(fila2)
        self.estado_baile = self._texto("", tenue=True)
        fl.addWidget(self.estado_baile)
        raiz.addWidget(caja)

    # ── Recarga ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _entero(v: Any, defecto: int) -> int:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return defecto

    @staticmethod
    def _flotante(v: Any, defecto: float) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return defecto

    def recargar(self) -> None:
        """Vuelve a leer config.json en los controles (sin guardar nada)."""
        self._cargando = True
        try:
            self.chk_alarmas.setChecked(bool(self._leer("alarmas", "activo", True)))
            self.chk_alarmas_grande.setChecked(bool(self._leer("alarmas", "pantalla_grande", True)))
            self.chk_decir.setChecked(bool(self._leer("alarmas", "decir_texto", True)))
            self.spin_bloqueo.setValue(self._entero(self._leer("alarmas", "bloqueo_s", 5), 5))
            self.spin_posponer.setValue(self._entero(self._leer("alarmas", "posponer_min", 5), 5))
            self.spin_recuperar.setValue(self._entero(self._leer("alarmas", "recuperar_min", 10), 10))
            vol = max(0.0, min(1.0, self._flotante(self._leer("alarmas", "volumen", 0.8), 0.8)))
            self.slider_volumen.setValue(int(round(vol * 100)))
            self.valor_volumen.setText(f"{self.slider_volumen.value()} %")
            i = self.combo_sonido.findData(str(self._leer("alarmas", "sonido", "azar") or "azar"))
            self.combo_sonido.setCurrentIndex(max(0, i))

            self.chk_salva.setChecked(bool(self._leer("salvapantallas", "activo", False)))
            paso = pg.paso_valido(self._leer("salvapantallas", "paso", 0))
            self.slider_paso.setValue(paso)
            self.valor_paso.setText(pg.etiqueta(paso))
            self.chk_clic_todo.setChecked(bool(self._leer("salvapantallas", "clic_sale_de_todo", True)))
            self.chk_fondo.setChecked(bool(self._leer("salvapantallas", "fondo_oscuro", True)))
            self.chk_reloj.setChecked(bool(self._leer("salvapantallas", "reloj", True)))

            self.chk_baile_auto.setChecked(bool(self._leer("baile", "auto", True)))
            umbral = max(UMBRAL_MIN, min(UMBRAL_MAX, self._flotante(self._leer("baile", "umbral", 0.05), 0.05)))
            self.slider_umbral.setValue(int(round(umbral * 100)))
            self.valor_umbral.setText(f"{umbral:.2f}")
            self.lista_apps.clear()
            for app in self._apps_config():
                self.lista_apps.addItem(app)
            self.chk_cambiar.setChecked(bool(self._leer("baile", "cambiar", False)))
            self.spin_cambiar.setValue(self._entero(self._leer("baile", "cambiar_s", 15), 15))
            self.chk_particulas.setChecked(bool(self._leer("baile", "particulas", True)))
        finally:
            self._cargando = False
        self._pintar_estado_grande()

    # ── Cambios con texto ────────────────────────────────────────────────────────
    def _al_volumen(self, valor: int) -> None:
        self.valor_volumen.setText(f"{int(valor)} %")
        self._poner("alarmas", "alarmas", "volumen", round(int(valor) / 100.0, 2))

    def _al_paso(self, valor: int) -> None:
        self.valor_paso.setText(pg.etiqueta(valor))
        self._poner("grande", "salvapantallas", "paso", pg.paso_valido(valor))

    def _al_umbral(self, valor: int) -> None:
        u = round(max(UMBRAL_MIN, min(UMBRAL_MAX, int(valor) / 100.0)), 2)
        self.valor_umbral.setText(f"{u:.2f}")
        self._poner("baile", "baile", "umbral", u)

    # ── Apps del baile ───────────────────────────────────────────────────────────
    def _apps_config(self) -> List[str]:
        out: List[str] = []
        for x in self._leer("baile", "apps", []) or []:
            n = normalizar_app(x)
            if n and n.lower() not in {a.lower() for a in out}:
                out.append(n)
        return out[:MAX_APPS]

    def apps(self) -> List[str]:
        return [self.lista_apps.item(i).text() for i in range(self.lista_apps.count())]

    def _anadir_app_escrita(self) -> None:
        if self.anadir_app(self.entrada_app.text()):
            self.entrada_app.clear()

    def anadir_app(self, nombre: Any) -> bool:
        n = normalizar_app(nombre)
        if not n:
            self._estado(self.estado_baile, "Ese nombre de app no vale.", error=True)
            return False
        actuales = self.apps()
        if n.lower() in {a.lower() for a in actuales}:
            return False
        if len(actuales) >= MAX_APPS:
            self._estado(self.estado_baile, f"Como mucho {MAX_APPS} apps.", error=True)
            return False
        self.lista_apps.addItem(n)
        self._poner("baile", "baile", "apps", self.apps())
        return True

    def quitar_app(self) -> bool:
        fila = self.lista_apps.currentRow()
        if fila < 0:
            return False
        self.lista_apps.takeItem(fila)
        self._poner("baile", "baile", "apps", self.apps())
        return True

    def apps_suenan(self) -> List[str]:
        """Las apps que suenan ahora (del detector de música) que aún no están."""
        r = _llamar(self.baile, "apps_sonando", True)
        ya = {a.lower() for a in self.apps()}
        out = []
        for x in r or ():
            n = normalizar_app(x)
            if n and n.lower() not in ya and n.lower() not in {o.lower() for o in out}:
                out.append(n)
        return out

    def _menu_suenan(self) -> None:
        apps = self.apps_suenan()
        menu = QMenu(self)
        if not apps:
            accion = menu.addAction("Ahora no suena ninguna otra app")
            accion.setEnabled(False)
        for n in apps:
            menu.addAction(n, lambda n=n: self.anadir_app(n))
        menu.exec(self.btn_suenan.mapToGlobal(self.btn_suenan.rect().bottomLeft()))

    # ── Botones ──────────────────────────────────────────────────────────────────
    def editar_alarmas(self) -> None:
        _llamar(self.alarmas, "abrir_dialogo", self)
        self._pintar_resumen_alarmas()

    def probar_alarma(self) -> bool:
        return bool(_llamar(self.alarmas, "probar"))

    def temporizador_rapido(self) -> None:
        r = _llamar(self.alarmas, "rapido", 5)
        if isinstance(r, dict) and r.get("ok") is False:
            self._estado(self.resumen_alarmas, str(r.get("error") or "No pude crear el temporizador."), error=True)
            return
        self._pintar_resumen_alarmas()

    def probar_salvapantallas(self) -> bool:
        self.guardar_ya()                               # probar lo que se ve, no lo guardado antes
        ok = bool(_llamar(self.grande, "probar_salvapantallas"))
        if not ok and self.grande is not None:
            motivo = str(getattr(self.grande, "ultimo_error", "") or "")
            self._estado(self.estado_grande, "Ahora no se puede probar" + (f": {motivo}." if motivo else "."),
                         error=True)
        return ok

    def alternar_grande(self) -> bool:
        r = bool(_llamar(self.grande, "alternar"))
        self._pintar_estado_grande()
        return r

    def alternar_baile(self) -> bool:
        b = self.baile
        if b is None:
            return False
        if getattr(b, "bailando", False):
            _llamar(b, "parar")
        else:
            _llamar(b, "bailar")
        self._pintar_estado_baile()
        return bool(getattr(b, "bailando", False))

    # ── Estado a la vista ────────────────────────────────────────────────────────
    def _pintar_resumen_alarmas(self, *_: Any) -> None:
        a = self.alarmas
        if a is None:
            self._estado(self.resumen_alarmas, "Las alarmas se editan con la app abierta.")
            return
        datos = _llamar(a, "listar")
        if not isinstance(datos, dict):
            self._estado(self.resumen_alarmas, "")
            return
        alarmas = [x for x in datos.get("alarmas") or [] if isinstance(x, dict)]
        temps = [x for x in datos.get("temporizadores") or [] if isinstance(x, dict)]
        activas = sum(1 for x in alarmas if x.get("activa", True))
        partes = [f"{activas} alarma{'s' if activas != 1 else ''} activa{'s' if activas != 1 else ''}"]
        if temps:
            partes.append(f"{len(temps)} temporizador{'es' if len(temps) != 1 else ''}")
        prox = datos.get("proxima")
        if isinstance(prox, dict) and prox.get("cuando_texto"):
            texto = f" «{prox.get('texto')}»" if prox.get("texto") else ""
            partes.append(f"la próxima {prox['cuando_texto']}{texto}")
        self._estado(self.resumen_alarmas, " · ".join(partes) + ".")

    def _pintar_estado_grande(self, *_: Any) -> None:
        atajo = texto_atajo(self.config, "pantalla_grande")
        g = self.grande
        est = _llamar(g, "estado") if g is not None else None
        activo = bool(isinstance(est, dict) and est.get("activo"))
        self.btn_grande.setText("SALIR DE PANTALLA GRANDE" if activo else "PANTALLA GRANDE")
        partes = []
        if atajo:
            partes.append(f"Atajo: {atajo}")
        if activo:
            partes.append("En pantalla grande ahora")
        self._estado(self.estado_grande, " · ".join(partes))

    def _pintar_estado_baile(self, *_: Any) -> None:
        b = self.baile
        if b is None:
            self.btn_bailar.setText("BAILAR")
            self._estado(self.estado_baile, "")
            return
        est = _llamar(b, "estado")
        est = est if isinstance(est, dict) else {}
        bailando = bool(getattr(b, "bailando", est.get("bailando", False)))
        self.btn_bailar.setText("PARAR" if bailando else "BAILAR")
        if bailando:
            app = str(est.get("app") or "")
            bpm = est.get("bpm")
            texto = "♪ Bailando" + (f" · {app}" if app else "") + (f" · {bpm:.0f} BPM" if isinstance(bpm, (int, float)) else "")
        else:
            texto = "En pausa hasta que la música pare." if est.get("pausado_hasta_silencio") else ""
        self._estado(self.estado_baile, texto)


__all__ = ("PanelOcioNativo", "SECCIONES", "normalizar_app", "sonidos", "texto_atajo")
