"""
ui/panel_escenario_nativo.py — Bailes MMD/VRMA (corte 9) y Minecraft (corte 10) en la
interfaz nativa.

La web tiene su vista y sus tarjetas (extra/bailes_mmd.jsx, extra/minecraft.jsx). La nativa
(ui/settings_panel.py) incrusta este panel, igual que PanelVidaNativo: cada apartado espera
300 ms quieto y escribe UNA vez, llama él mismo a `recargar_config()` del controlador de ese
apartado y emite `cambiado(str seccion)`.

- BAILES (`bailes`): el reproductor (anterior, reproducir, pausa, parar, siguiente, con lo que
  suena y el tiempo), la biblioteca (doble clic = bailar; importar con el diálogo de archivos,
  abrir la carpeta, quitar, favorito, no sale al azar) y los ajustes: volumen, al terminar
  (parar, siguiente, repetir, aleatorio) y en el sitio (config.json baile.*). Con la mascota
  animada o los sprites avisa «esta mascota no tiene esqueleto: baila a su manera».
- MINECRAFT (`minecraft`): reacciones a tu partida (config.json minecraft.*: reaccionar, ruta
  del latest.log con «Detectar», voz, decir en el juego, resumen al salir, pensar en juego,
  reaccionar a otros) y el bot (datos.json con nucleo.datos.guardar_minecraft: servidor,
  puerto, versión, nick, dueño, solo el dueño —con el aviso de suplantación—, defender, pensar
  cada N s, estilo), «Instalar el bot (~400 MB)» (D3: solo con este botón), conectar y
  desconectar, y el aviso de online-mode=false («Abrir en LAN» de vanilla no sirve).

    panel = PanelEscenarioNativo(config)
    panel.enlazar(servicios_c4)  # ServiciosCorte4 (usa .escenario) o ServiciosEscenario; se suelta solo
    panel.guardar_ya()           # en el «Guardar» de Ajustes

Estilo de ui/theme.py (COLORS), como el resto de la nativa. Los textos que vienen de fuera
(títulos de bailes, nick, errores del bot) van como texto plano, nunca como HTML.
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

_log = logging.getLogger("lune.panel_escenario")

SECCIONES = ("bailes", "minecraft")
ESPERA_GUARDADO_MS = 300
AL_TERMINAR = (("parar", "Parar"), ("siguiente", "Siguiente baile"), ("repetir", "Repetir el mismo"),
               ("aleatorio", "Uno al azar"))
ESTILOS = (("personaje", "Como Lune (su personaje)"), ("sobrio", "Sobrio"))
CONFIG_MC = (("reaccionar", "Reaccionar a lo que pasa en tu partida (latest.log)"),
             ("voz_reacciones", "Decir las reacciones en voz alta"),
             ("auto_con_juego", "Solo mientras Minecraft está abierto"),
             ("decir_en_juego", "En modo juego, que lo diga el bot en el chat del juego"),
             ("resumen_al_salir", "Al salir del modo juego, un resumen"),
             ("pensar_en_juego", "Que el bot piense solo mientras juegas (usa más GPU)"),
             ("reaccionar_otros", "Reaccionar también a otros jugadores"))
_NICK = re.compile(r"^[A-Za-z0-9_]{3,16}$")
_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_HOST = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,253}$")
AVISO_SIN_ESQUELETO = "Esta mascota no tiene esqueleto: baila a su manera (suena la canción y baila al ritmo)."
AVISO_SUPLANTACION = ("Ojo: en un servidor sin autenticación (online-mode=false) cualquiera puede ponerse tu nick. "
                      "«Solo el dueño» filtra por nombre, no es una garantía de seguridad.")
AVISO_ONLINE_MODE = ("El bot solo entra en servidores sin autenticación (online-mode=false): uno local o uno tuyo con "
                     "esa opción. «Abrir en LAN» de Minecraft normal no sirve (pide cuenta). Sin visor ni puertos abiertos.")
TEXTO_INSTALAR = "INSTALAR EL BOT (~400 MB)"


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
        _log.exception("panel escenario: no pude guardar")
        return False


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("panel escenario: %s.%s falló", type(obj).__name__, metodo)
        return None


def _limpio(v: Any, n: int = 160) -> str:
    return re.sub(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]", "", str(v or ""))[:n].strip()


def mmss(s: Any) -> str:
    try:
        t = max(0, int(float(s)))
    except (TypeError, ValueError):
        t = 0
    return f"{t // 60}:{t % 60:02d}"


def texto_mmd(e: Any) -> str:
    """«Bailando «X» · 1:23 / 3:45» (con el estado ya normalizado por el puente)."""
    from ui.puente_escenario import estado_mmd
    d = estado_mmd(e, servicio=True)
    t = f" · {mmss(d['t'])} / {mmss(d['total'])}" if d["total"] else ""
    titulo = f"«{d['titulo']}»" if d["titulo"] else "un baile"
    if d["fase"] == "error":
        return f"No pude bailar: {d['error']}" if d["error"] else "No pude bailar."
    if d["pendiente"]:
        return f"Saco a la mascota para bailar {titulo}…"
    if d["fase"] == "cargando":
        return f"Preparando {titulo}…" + (" (escuchando el ritmo)" if d["analizando"] else "")
    if d["cedida"]:
        return f"En pausa mientras dura el juego, la alarma o la pantalla grande: {titulo}{t}"
    if d["fase"] == "pausado" or d["pausado"]:
        return f"En pausa: {titulo}{t}"
    if d["fase"] in ("sonando", "listo", "saliendo"):
        return f"Bailando {titulo}{t}"
    return "Parada."


def texto_bot(e: Any) -> str:
    from ui.puente_escenario import estado_mc
    b = estado_mc(e, servicio=True)
    bot, req = b["bot"], b["requisitos"]
    if req["node_ok"] is False:
        return "Hace falta Node.js 18 o más nuevo (nodejs.org) para el bot."
    if bot["instalando"]:
        return "Instalando el bot (~400 MB)… puede tardar unos minutos."
    if not bot["instalado"]:
        return "El bot no está instalado: pulsa «Instalar el bot»."
    if bot["conectado"]:
        extra = f" · vida {bot['vida']}/20" if bot["vida"] is not None else ""
        return f"Conectado a {bot['servidor'] or 'el servidor'} como {bot['nick'] or 'Lune'}{extra}."
    if bot["conectando"]:
        return f"Conectando a {bot['servidor'] or 'el servidor'}…"
    err = bot["error"]
    return f"Desconectado: {err}" if err else "Desconectado."


class PanelEscenarioNativo(QWidget):
    """Bailes MMD/VRMA y Minecraft para la nativa."""

    cambiado = pyqtSignal(str)

    def __init__(self, config: Any = None, parent: Optional[QWidget] = None, *,
                 retardo_ms: int = ESPERA_GUARDADO_MS, datos: Any = None,
                 rutas_log: Optional[Callable[[], List[Any]]] = None):
        super().__init__(parent)
        self.config = config
        self.mmd: Any = None
        self.minecraft: Any = None
        self._datos = datos
        self._rutas_log = rutas_log
        self._enganchados: List[Any] = []
        self._pendientes: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._pend_bot: Dict[str, Any] = {}
        self._cargando = False
        self.ultimo_guardado: Dict[str, Dict[Any, Any]] = {}
        self._conectados: List[Tuple[Any, Callable]] = []
        self._bailes: List[Dict[str, Any]] = []

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(retardo_ms)))
        self._timer.timeout.connect(self.guardar_ya)

        self._construir()
        self.recargar()
        self._pintar_servicios()

    # ── Servicios ────────────────────────────────────────────────────────────────
    def enlazar(self, escenario: Any = None, *, mmd: Any = None, minecraft: Any = None) -> None:
        """Los controladores llegan (o cambian) después de construir el panel: `enlazar(servicios)`
        (ServiciosCorte4 con `.escenario`, un ServiciosEscenario) o por nombre. None los suelta.
        Se apunta en `_deshacer` de lo que se le da: al desmontar (cambio de interfaz, salir) los
        suelta antes de que se borren."""
        self._desconectar_servicios()
        if escenario is not None:
            from ui.puente_escenario import controladores_escenario
            c = controladores_escenario(escenario)
            mmd = c["mmd"] if c["mmd"] is not None else mmd
            minecraft = c["minecraft"] if c["minecraft"] is not None else minecraft
        self.mmd, self.minecraft = mmd, minecraft
        self._conectar_servicios()
        self._pintar_servicios()
        _llamar(self.mmd, "refrescar")
        deshacer = getattr(escenario, "_deshacer", None) if escenario is not None else None
        if isinstance(deshacer, list) and not any(x is escenario for x in self._enganchados):
            self._enganchados.append(escenario)
            mios = (mmd, minecraft)

            def soltar() -> None:
                try:
                    if (self.mmd, self.minecraft) == mios:
                        self.enlazar(None)
                except RuntimeError:                       # el panel ya se borró
                    pass
            deshacer.append(soltar)

    def _conectar_servicios(self) -> None:
        for obj, senal, slot in ((self.mmd, "estado_cambio", self._pintar_mmd),
                                 (self.mmd, "biblioteca_cambio", self._al_biblioteca),
                                 (self.mmd, "importado", self._al_importado),
                                 (self.minecraft, "estado_cambio", self._pintar_mc)):
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
        m, mc = self.mmd is not None, self.minecraft is not None
        for w in self._botones_mmd:
            w.setEnabled(m)
        for w in (self.btn_instalar, self.btn_conectar, self.btn_desconectar):
            w.setEnabled(mc)
        if not m:
            self._bailes = []
            self.lista.clear()
        self._pintar_mmd()
        self._pintar_mc()

    def showEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        _llamar(self.mmd, "refrescar")                                 # la carpeta puede haber cambiado
        super().showEvent(ev)

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

    def _poner_bot(self, clave: str, valor: Any) -> None:
        if self._cargando:
            return
        self._pend_bot[clave] = valor
        self._timer.start()

    def _quitar_bot(self, clave: str) -> None:
        self._pend_bot.pop(clave, None)

    @property
    def pendiente(self) -> bool:
        return any(self._pendientes.values()) or bool(self._pend_bot)

    def _mod_datos(self) -> Any:
        if self._datos is None:
            try:
                from nucleo import datos
                self._datos = datos
            except Exception:
                return None
        return self._datos

    def guardar_ya(self) -> List[str]:
        """Escribe ya lo pendiente (config.json en una sola escritura; datos.json del bot con
        guardar_minecraft), aplica en caliente (`recargar_config`) y emite `cambiado`."""
        self._timer.stop()
        pend = {s: c for s, c in self._pendientes.items() if c}
        bot, self._pend_bot = self._pend_bot, {}
        self._pendientes = {}
        hechas: List[str] = []
        if bot:
            mod = self._mod_datos()
            f = getattr(mod, "guardar_minecraft", None) if mod is not None else None
            try:
                if not callable(f):
                    raise ValueError("No puedo guardar los datos del bot en esta versión.")
                f(dict(bot))
                self._estado(self.error_bot, "")
                self.ultimo_guardado["bot"] = dict(bot)
                if "minecraft" not in hechas:
                    hechas.append("minecraft")
            except ValueError as e:
                self._estado(self.error_bot, _limpio(e, 300), error=True)
            except Exception:
                _log.exception("panel escenario: guardar datos.json")
                self._estado(self.error_bot, "No pude guardar los datos del bot (datos.json).", error=True)
        if pend:
            todo: Dict[Tuple[str, str], Any] = {}
            for s in SECCIONES:
                todo.update(pend.get(s, {}))
            if not _escribir(self.config, todo):
                self._estado(self.estado_general, "No pude guardar en config.json.", error=True)
            else:
                for s in SECCIONES:
                    if s in pend:
                        self.ultimo_guardado[s] = dict(pend[s])
                        if s not in hechas:
                            hechas.append(s)
        hechas = [s for s in SECCIONES if s in hechas]
        ctl = {"bailes": self.mmd, "minecraft": self.minecraft}
        for s in hechas:
            _llamar(ctl[s], "recargar_config")
            self.cambiado.emit(s)
        if hechas:
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
        lbl.setTextFormat(Qt.TextFormat.PlainText)          # nada de HTML de fuera (títulos, nick…)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{COLORS['text_muted' if tenue else 'text']};border:none;background:transparent;")
        return lbl

    def _sub(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{COLORS['text_muted']};border:none;letter-spacing:1px;padding-top:4px;")
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
        s.setFixedWidth(110)
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
        ancho = isinstance(widget, (QComboBox, QLineEdit, QSlider))
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
        self.setObjectName("escenarioPanel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)
        self._construir_bailes(raiz)
        self._construir_minecraft(raiz)
        self.estado_general = self._texto("", tenue=True)
        raiz.addWidget(self.estado_general)

    def _construir_bailes(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("BAILES"))
        caja, fl = self._caja("bailesCaja")
        fl.addWidget(self._texto("Mete en la carpeta «bailes» un .vmd (o un .vrma) con su canción, o impórtalos. "
                                 "Lune los baila con su cuerpo; al pausar o parar vuelve al reposo con los brazos abajo.",
                                 tenue=True))
        self.estado_mmd = self._texto("")
        self.estado_mmd.setFont(QFont(FONT_MONO, 10))
        fl.addWidget(self.estado_mmd)
        self.aviso_esqueleto = self._texto(AVISO_SIN_ESQUELETO)
        self._estado(self.aviso_esqueleto, AVISO_SIN_ESQUELETO, aviso=True)
        self.aviso_esqueleto.setVisible(False)
        fl.addWidget(self.aviso_esqueleto)
        self.btn_anterior = self._boton("⏮")
        self.btn_anterior.setToolTip("Anterior")
        self.btn_anterior.clicked.connect(self.anterior)
        self.btn_reproducir = self._boton("▶ BAILAR", principal=True)
        self.btn_reproducir.clicked.connect(self.reproducir)
        self.btn_pausa = self._boton("⏸ PAUSA")
        self.btn_pausa.clicked.connect(self.pausa)
        self.btn_parar = self._boton("⏹ PARAR")
        self.btn_parar.clicked.connect(self.parar)
        self.btn_siguiente = self._boton("⏭")
        self.btn_siguiente.setToolTip("Siguiente")
        self.btn_siguiente.clicked.connect(self.siguiente)
        self._botones(fl, self.btn_anterior, self.btn_reproducir, self.btn_pausa, self.btn_parar, self.btn_siguiente)

        self.lista = QListWidget()
        self.lista.setMinimumHeight(150)
        self.lista.setStyleSheet(
            f"QListWidget{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};color:{COLORS['text']};}}"
            f"QListWidget::item:selected{{background:{COLORS['accent']};color:{COLORS['bg']};}}")
        self.lista.itemDoubleClicked.connect(lambda it: self.reproducir(it.data(Qt.ItemDataRole.UserRole)))
        fl.addWidget(self.lista)
        self.btn_importar = self._boton("IMPORTAR…", principal=True)
        self.btn_importar.clicked.connect(self.importar)
        self.btn_carpeta = self._boton("ABRIR CARPETA")
        self.btn_carpeta.clicked.connect(self.abrir_carpeta)
        self.btn_favorito = self._boton("★ FAVORITO")
        self.btn_favorito.clicked.connect(self.alternar_favorito)
        self.btn_desactivar = self._boton("NO AL AZAR")
        self.btn_desactivar.setToolTip("No sale en «siguiente» ni al azar (se puede poner a mano).")
        self.btn_desactivar.clicked.connect(self.alternar_desactivado)
        self.btn_quitar = self._boton("QUITAR")
        self.btn_quitar.setToolTip("Lo mueve a bailes/.quitados (no se borra).")
        self.btn_quitar.clicked.connect(self.quitar)
        self._botones(fl, self.btn_importar, self.btn_carpeta, self.btn_favorito, self.btn_desactivar, self.btn_quitar)
        self.msg_bailes = self._texto("", tenue=True)
        fl.addWidget(self.msg_bailes)
        self._botones_mmd = (self.btn_anterior, self.btn_reproducir, self.btn_pausa, self.btn_parar,
                             self.btn_siguiente, self.btn_importar, self.btn_carpeta, self.btn_favorito,
                             self.btn_desactivar, self.btn_quitar)

        fl.addWidget(self._sub("AJUSTES"))
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.lbl_vol = self._texto("")
        self.slider_vol.valueChanged.connect(self._al_volumen)
        fl.addLayout(self._fila("Volumen de la canción", self.slider_vol, self.lbl_vol))
        self.combo_al_terminar = self._combo()
        for clave, texto in AL_TERMINAR:
            self.combo_al_terminar.addItem(texto, clave)
        self.combo_al_terminar.currentIndexChanged.connect(
            lambda *_: self._poner("bailes", "baile", "al_terminar", self.combo_al_terminar.currentData()))
        fl.addLayout(self._fila("Al terminar", self.combo_al_terminar))
        self.chk_en_sitio = self._check("Bailar en el sitio (sin desplazarse)",
                                        "Algunos bailes caminan por el escenario; así se queda donde está.")
        self.chk_en_sitio.toggled.connect(lambda v: self._poner("bailes", "baile", "en_el_sitio", bool(v)))
        fl.addWidget(self.chk_en_sitio)
        raiz.addWidget(caja)

    def _construir_minecraft(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("MINECRAFT"))
        caja, fl = self._caja("minecraftCaja")
        fl.addWidget(self._sub("REACCIONES A TU PARTIDA"))
        self.checks_mc: Dict[str, QCheckBox] = {}
        for clave, texto in CONFIG_MC:
            c = self._check(texto)
            c.toggled.connect(lambda v, k=clave: self._poner("minecraft", "minecraft", k, bool(v)))
            self.checks_mc[clave] = c
            fl.addWidget(c)
        self.linea_log = self._linea("automático (.minecraft, Prism, MultiMC, CurseForge…)", 1024)
        self.linea_log.setToolTip("El latest.log de tu Minecraft. Vacío = buscarlo solo.")
        self.linea_log.textChanged.connect(self._al_ruta_log)
        self.btn_detectar = self._boton("DETECTAR")
        self.btn_detectar.clicked.connect(self.detectar_log)
        fl.addLayout(self._fila("Registro (latest.log)", self.linea_log, self.btn_detectar))
        self.error_log = self._texto("", tenue=True)
        fl.addWidget(self.error_log)

        fl.addWidget(self._sub("BOT DE MINECRAFT"))
        fl.addWidget(self._texto(AVISO_ONLINE_MODE, tenue=True))
        self.linea_host = self._linea("localhost", 253)
        self.linea_host.textChanged.connect(self._al_host)
        self.spin_puerto = self._spin(1, 65535)
        self.spin_puerto.valueChanged.connect(lambda v: self._poner_bot("port", int(v)))
        fl.addLayout(self._fila("Servidor", self.linea_host, self.spin_puerto))
        self.linea_version = self._linea("vacío = la detecta", 12)
        self.linea_version.textChanged.connect(self._al_version)
        fl.addLayout(self._fila("Versión", self.linea_version))
        self.linea_usuario = self._linea("vacío = el nombre de Lune", 16)
        self.linea_usuario.textChanged.connect(lambda t: self._al_nick("usuario", t))
        fl.addLayout(self._fila("Nick del bot", self.linea_usuario))
        self.linea_dueno = self._linea("tu nick de Minecraft", 16)
        self.linea_dueno.textChanged.connect(lambda t: self._al_nick("dueno", t))
        fl.addLayout(self._fila("Tu nick (dueño)", self.linea_dueno))
        self.chk_solo_dueno = self._check("Solo obedece al dueño")
        self.chk_solo_dueno.toggled.connect(self._al_solo_dueno)
        fl.addWidget(self.chk_solo_dueno)
        self.aviso_suplantacion = self._texto(AVISO_SUPLANTACION)
        self._estado(self.aviso_suplantacion, AVISO_SUPLANTACION, aviso=True)
        fl.addWidget(self.aviso_suplantacion)
        self.chk_defender = self._check("Te defiende de los monstruos")
        self.chk_defender.toggled.connect(lambda v: self._poner_bot("defender", bool(v)))
        fl.addWidget(self.chk_defender)
        self.spin_pensar = self._spin(30, 3600, " s")
        self.spin_pensar.setToolTip("Cada cuánto piensa qué hacer por su cuenta (comparte el modelo con el chat).")
        self.spin_pensar.valueChanged.connect(lambda v: self._poner_bot("pensar_cada_s", int(v)))
        fl.addLayout(self._fila("Pensar cada", self.spin_pensar))
        self.combo_estilo = self._combo()
        for clave, texto in ESTILOS:
            self.combo_estilo.addItem(texto, clave)
        self.combo_estilo.currentIndexChanged.connect(
            lambda *_: self._poner_bot("estilo_frases", self.combo_estilo.currentData()))
        fl.addLayout(self._fila("Cómo habla en el chat", self.combo_estilo))
        self.error_bot = self._texto("", tenue=True)
        fl.addWidget(self.error_bot)
        self.btn_instalar = self._boton(TEXTO_INSTALAR, principal=True)
        self.btn_instalar.setToolTip("Descarga las dependencias del bot con npm (sin scripts). Solo hace falta una vez.")
        self.btn_instalar.clicked.connect(self.instalar_bot)
        self.btn_conectar = self._boton("CONECTAR", principal=True)
        self.btn_conectar.clicked.connect(self.conectar_bot)
        self.btn_desconectar = self._boton("DESCONECTAR")
        self.btn_desconectar.clicked.connect(self.desconectar_bot)
        self._botones(fl, self.btn_instalar, self.btn_conectar, self.btn_desconectar)
        self.estado_bot = self._texto("", tenue=True)
        fl.addWidget(self.estado_bot)
        self.estado_reacciones = self._texto("", tenue=True)
        fl.addWidget(self.estado_reacciones)
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

    def _bot_guardado(self) -> Dict[str, Any]:
        from ui.puente_escenario import BOT_DEFECTO, bot_para_pagina
        mod = self._mod_datos()
        try:
            crudo = mod.minecraft() if mod is not None else None
        except Exception:
            _log.exception("panel escenario: leer datos.json")
            crudo = None
        return bot_para_pagina(crudo) if isinstance(crudo, dict) else dict(BOT_DEFECTO)

    def recargar(self) -> None:
        """Vuelve a leer config.json y datos.json en los controles (sin guardar nada)."""
        from ui.puente_escenario import CONFIG_MC_DEFECTO
        self._cargando = True
        try:
            try:
                vol = float(self._leer("baile", "volumen", 0.25))
            except (TypeError, ValueError):
                vol = 0.25
            self.slider_vol.setValue(max(0, min(100, round(vol * 100))))
            self.lbl_vol.setText(f"{self.slider_vol.value()} %")
            al = self._leer("baile", "al_terminar", "parar")
            self.combo_al_terminar.setCurrentIndex(max(0, self.combo_al_terminar.findData(
                al if al in dict(AL_TERMINAR) else "parar")))
            self.chk_en_sitio.setChecked(self._leer("baile", "en_el_sitio", True) is not False)

            for clave, c in self.checks_mc.items():
                v = self._leer("minecraft", clave, CONFIG_MC_DEFECTO[clave])
                c.setChecked(v if isinstance(v, bool) else CONFIG_MC_DEFECTO[clave])
            ruta = self._leer("minecraft", "ruta_log", "")
            self.linea_log.setText(ruta if isinstance(ruta, str) else "")
            self._estado(self.error_log, "")

            b = self._bot_guardado()
            self.linea_host.setText(b["host"])
            self.spin_puerto.setValue(b["port"])
            self.linea_version.setText(b["version"])
            self.linea_usuario.setText(b["usuario"])
            self.linea_dueno.setText(b["dueno"])
            self.chk_solo_dueno.setChecked(bool(b["solo_dueno"]))
            self.chk_defender.setChecked(bool(b["defender"]))
            self.spin_pensar.setValue(max(30, min(3600, b["pensar_cada_s"])))
            self.combo_estilo.setCurrentIndex(max(0, self.combo_estilo.findData(b["estilo_frases"])))
            self._estado(self.error_bot, "")
        finally:
            self._cargando = False
        self.aviso_suplantacion.setVisible(self.chk_solo_dueno.isChecked())

    # ── Cambios con validación ───────────────────────────────────────────────────
    def _al_volumen(self, v: int) -> None:
        self.lbl_vol.setText(f"{int(v)} %")
        self._poner("bailes", "baile", "volumen", round(int(v) / 100.0, 3))

    def _al_ruta_log(self, texto: str) -> None:
        t = str(texto or "").strip()
        if t:
            try:
                from lune_core.minecraft_log import ruta_valida
                ok = ruta_valida(t) is not None
            except Exception:
                ok = t.lower().endswith("latest.log") and not t.startswith(("\\\\", "//"))
            if not ok:
                self._pendientes.get("minecraft", {}).pop(("minecraft", "ruta_log"), None)
                self._estado(self.error_log, "Tiene que ser un archivo latest.log de tu disco (no de la red).",
                             error=True)
                return
        self._estado(self.error_log, "")
        self._poner("minecraft", "minecraft", "ruta_log", t)

    def _al_host(self, texto: str) -> None:
        t = str(texto or "").strip()
        if not t or not _HOST.match(t) or "://" in t:
            self._quitar_bot("host")
            if not self._cargando:
                self._estado(self.error_bot, "El servidor es un nombre o una IP (sin http:// ni rutas).", error=True)
            return
        self._estado(self.error_bot, "")
        self._poner_bot("host", t)

    def _al_version(self, texto: str) -> None:
        t = str(texto or "").strip()
        if t and not _VERSION.match(t):
            self._quitar_bot("version")
            if not self._cargando:
                self._estado(self.error_bot, "La versión es como 1.21.1 (o vacía para detectarla).", error=True)
            return
        self._estado(self.error_bot, "")
        self._poner_bot("version", t)

    def _al_nick(self, clave: str, texto: str) -> None:
        t = str(texto or "").strip()
        if t and not _NICK.match(t):
            self._quitar_bot(clave)
            if not self._cargando:
                self._estado(self.error_bot, "Los nicks tienen de 3 a 16 letras, números o _.", error=True)
            return
        self._estado(self.error_bot, "")
        self._poner_bot(clave, t)

    def _al_solo_dueno(self, v: bool) -> None:
        self.aviso_suplantacion.setVisible(bool(v))
        self._poner_bot("solo_dueno", bool(v))

    # ── Botones: bailes ──────────────────────────────────────────────────────────
    def _seleccionado(self) -> Optional[Dict[str, Any]]:
        it = self.lista.currentItem()
        id_ = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
        return next((b for b in self._bailes if b["id"] == id_), None)

    def _msg(self, r: Any, ok_texto: str = "") -> bool:
        ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (bool(r), ok_texto))
        if texto:
            self._estado(self.msg_bailes, _limpio(texto, 300), error=not ok)
        return bool(ok)

    def reproducir(self, id_: Any = None) -> bool:
        if self.mmd is None:
            return False
        if not isinstance(id_, str) or not id_:
            b = self._seleccionado()
            id_ = b["id"] if b is not None else None
        ok = self._msg(_llamar(self.mmd, "reproducir", id_ or None, origen="usuario"))
        self._pintar_mmd()
        return ok

    def pausa(self) -> bool:
        r = _llamar(self.mmd, "pausa") is True
        self._pintar_mmd()
        return r

    def parar(self) -> bool:
        r = _llamar(self.mmd, "parar") is True
        self._pintar_mmd()
        return r

    def siguiente(self) -> bool:
        return self._msg(_llamar(self.mmd, "siguiente"))

    def anterior(self) -> bool:
        return self._msg(_llamar(self.mmd, "anterior"))

    def importar(self) -> None:
        _llamar(self.mmd, "importar_dialogo", self.window())

    def abrir_carpeta(self) -> bool:
        return _llamar(self.mmd, "abrir_carpeta") is True

    def alternar_favorito(self) -> bool:
        b = self._seleccionado()
        return b is not None and _llamar(self.mmd, "favorito", b["id"], not b["favorito"]) is True

    def alternar_desactivado(self) -> bool:
        b = self._seleccionado()
        return b is not None and _llamar(self.mmd, "desactivar", b["id"], not b["desactivado"]) is True

    def quitar(self) -> bool:
        b = self._seleccionado()
        if b is None:
            return False
        return self._msg(_llamar(self.mmd, "quitar", b["id"]))

    # ── Botones: Minecraft ───────────────────────────────────────────────────────
    def detectar_log(self) -> str:
        """Pone en el campo el latest.log más reciente de los sitios de siempre (solo stat)."""
        f = self._rutas_log
        try:
            if f is None:
                from lune_core.minecraft_log import rutas_candidatas
                f = rutas_candidatas
            rutas = list(f() or [])[:64]
            from lune_core.minecraft_log import elegir_log
            p = elegir_log("", rutas, reciente_s=None) if rutas else None
        except Exception:
            _log.exception("panel escenario: detectar latest.log")
            p = None
        if p is None:
            self._estado(self.error_log, "No encontré ningún latest.log de Minecraft. Ábrelo una vez y vuelve a probar.",
                         aviso=True)
            return ""
        self.linea_log.setText(str(p))
        self._estado(self.error_log, f"Encontrado: {p}")
        return str(p)

    def instalar_bot(self) -> None:
        """D3: la instalación (~400 MB) solo la dispara este botón."""
        _llamar(self.minecraft, "instalar_bot")
        self._pintar_mc()

    def conectar_bot(self) -> bool:
        self.guardar_ya()                                   # con lo último escrito
        r = _llamar(self.minecraft, "conectar_bot")
        ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (False, ""))
        self._pintar_mc()
        if texto:
            self._estado(self.estado_bot, _limpio(texto, 300), error=not ok)
        return bool(ok)

    def desconectar_bot(self) -> bool:
        r = _llamar(self.minecraft, "desconectar_bot") is True
        self._pintar_mc()
        return r

    # ── Estado a la vista ────────────────────────────────────────────────────────
    def _al_biblioteca(self, payload: Any = None) -> None:
        from ui.puente_escenario import _leer_controlador, lista_bailes
        lista = _leer_controlador(payload, list) if isinstance(payload, str) else payload
        self._pintar_lista(lista_bailes(lista))

    def _pintar_lista(self, bailes: List[Dict[str, Any]]) -> None:
        actual = self._seleccionado()
        self._bailes = list(bailes)
        self.lista.clear()
        for b in self._bailes:
            autores = " · ".join(x for x in (b["autor_cancion"], b["autor_mmd"]) if x)
            texto = ("★ " if b["favorito"] else "") + b["titulo"] + (f" — {autores}" if autores else "")
            if b["duracion"]:
                texto += f"  ({mmss(b['duracion'])})"
            if b["desactivado"]:
                texto += "  [no al azar]"
            if b["problema"]:
                texto += f"  ⚠ {b['problema']}"
            elif not b["audio"]:
                texto += "  (sin canción)"
            it = QListWidgetItem(texto)
            it.setData(Qt.ItemDataRole.UserRole, b["id"])
            self.lista.addItem(it)
            if actual is not None and actual["id"] == b["id"]:
                self.lista.setCurrentItem(it)

    def _al_importado(self, payload: Any = None) -> None:
        from ui.puente_escenario import _leer_controlador
        o = _leer_controlador(payload, dict) if isinstance(payload, str) else payload
        if isinstance(o, dict):
            self._estado(self.msg_bailes, _limpio(o.get("texto"), 300), error=o.get("ok") is not True)

    def estado_mmd_dict(self) -> Dict[str, Any]:
        from ui.puente_escenario import estado_mmd
        e = _llamar(self.mmd, "estado") if self.mmd is not None else None
        return estado_mmd(e, servicio=self.mmd is not None)

    def _pintar_mmd(self, *_: Any) -> None:
        e = self.estado_mmd_dict()
        if self.mmd is None:
            self._estado(self.estado_mmd, "Los bailes van con la app abierta (servicios de escritorio).")
            self.aviso_esqueleto.setVisible(False)
            return
        self._estado(self.estado_mmd, texto_mmd(e), error=e["fase"] == "error")
        self.aviso_esqueleto.setVisible(bool(e["sin_esqueleto"]))
        puesto = e["fase"] not in ("parado", "error") or e["pendiente"]
        self.btn_pausa.setText("▶ SEGUIR" if e["pausado"] and not e["cedida"] else "⏸ PAUSA")
        self.btn_pausa.setEnabled(puesto)
        self.btn_parar.setEnabled(puesto)

    def estado_mc_dict(self) -> Dict[str, Any]:
        from ui.puente_escenario import estado_mc
        e = _llamar(self.minecraft, "estado") if self.minecraft is not None else None
        return estado_mc(e, reaccionar=self._leer("minecraft", "reaccionar", False) is True,
                         servicio=self.minecraft is not None)

    def _pintar_mc(self, *_: Any) -> None:
        e = self.estado_mc_dict()
        if self.minecraft is None:
            self._estado(self.estado_bot, "El bot y las reacciones van con la app abierta.")
            self._estado(self.estado_reacciones, "")
            return
        bot = e["bot"]
        self._estado(self.estado_bot, texto_bot(e), error=bool(bot["error"]) and not bot["conectado"])
        self.btn_instalar.setEnabled(not bot["instalando"] and e["requisitos"]["node_ok"] is not False)
        self.btn_instalar.setText("INSTALANDO…" if bot["instalando"] else
                                  ("REINSTALAR EL BOT" if bot["instalado"] else TEXTO_INSTALAR))
        self.btn_conectar.setEnabled(bot["instalado"] and not bot["conectado"] and not bot["conectando"])
        self.btn_desconectar.setEnabled(bot["conectado"] or bot["conectando"])
        if not e["reaccionar"]:
            txt = "Reacciones apagadas."
        elif e["log"]["activo"]:
            txt = f"Leyendo tu partida{' como ' + e['log']['yo'] if e['log']['yo'] else ''}."
        else:
            txt = "Esperando a que abras Minecraft."
        self._estado(self.estado_reacciones, txt)


__all__ = ("PanelEscenarioNativo", "SECCIONES", "AVISO_SIN_ESQUELETO", "AVISO_SUPLANTACION", "AVISO_ONLINE_MODE",
           "texto_mmd", "texto_bot", "mmss")
