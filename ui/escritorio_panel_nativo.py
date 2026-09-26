"""
ui/escritorio_panel_nativo.py — Ajustes de escritorio del corte 4 en la interfaz nativa.

La web tiene sus tarjetas (extra/apariencia.jsx, extra/juego.jsx). La nativa
(ui/settings_panel.py) incrusta este panel, con cinco apartados que guardan al
momento (como VrmPanelNativo: esperan 300 ms quietos y escriben UNA vez en
config.json con `config.config[...]` + `config.save()`):

- TEMA (`tema`): preset, tono 0–359°, saturación 0–200 %, teñir amarillo y
  fondos, Restablecer y la muestra de la paleta. Aviso: la ventana nativa se
  recolorea al reiniciar (ui.theme.aplicar_tema al arrancar); la mascota, la
  bandeja y el menú radial cambian al momento (ControlTema.recargar).
- MODO JUEGO (`juego`): detectar, qué hacer con la mascota, sus FPS, qué cuenta
  como juego, prioridad, RAM, silenciar y la lista de .exe (con «De las
  abiertas…» si hay `apps_visibles`).
- RENDIMIENTO (`rendimiento`): avatar.fps_max, avatar.siempre_encima,
  sistema.recorte_ram_auto, interfaz.en_barra_tareas y «Liberar memoria ahora»
  si hay `liberar_memoria`.
- ATAJOS (`atajos`): activo, pausar en juegos, sonido y un combo por atajo con
  «Detectar» (el campo captura la tecla; los atajos globales se pausan mientras,
  con `atajos.capturando(True/False)` si se pasa el gestor). Se validan con
  servicios.atajos_globales.comprobar (errores no se guardan; los avisos sí) y
  sin duplicados.
- MENÚ RADIAL (`radial`): los botones de menu_radial.principal (hasta 10, sin
  repetir, en orden) y los sonidos de menú (menu.sonidos, menu.volumen).

Señal `cambiado(str seccion)` tras escribir cada apartado (uno de SECCIONES).
Quien lo integra aplica en caliente: tema → ControlTema.recargar(); juego →
ControlModoJuego.recargar_config(); atajos → GestorAtajosQt.recargar();
rendimiento → mascota.set_fps_max / set_encima…; radial → nada (se lee al abrir).

    panel = PanelEscritorioNativo(config, atajos=servicios.atajos)
    panel.cambiado.connect(lambda s: aplicar(s, panel.ultimo_guardado.get(s)))
    panel.set_atajos(gestor)      # si el gestor llega después (la nativa monta al final)

Estilo de ui/theme.py (COLORS), como el resto de la nativa.
"""
from __future__ import annotations

import copy
import re
from pathlib import PureWindowsPath
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QSizePolicy, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from nucleo import tema
from servicios import atajos_globales as ag
from ui.tema_qt import escribir_claves
from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

SECCIONES = ("tema", "juego", "rendimiento", "atajos", "radial")
ESPERA_GUARDADO_MS = 300
CAPTURA_MS = 15000
MAX_RADIAL = 10
MAX_APPS = 200

ACCIONES_JUEGO = (("ocultar", "Esconder la mascota"), ("fondo", "Mandarla al fondo"),
                  ("nada", "No hacer nada"))

# Etiquetas si nucleo/acciones_ui.py (el catálogo común) aún no está.
_ETIQUETAS = {
    "mostrar_lune": "Mostrar Lune", "mascota": "Sacar / esconder la mascota",
    "menu_radial": "Menú radial", "comentar": "Comentar la pantalla", "voz": "Voz",
    "llamada": "Llamada", "fantasma": "Modo fantasma", "dormir": "Dormir / despertar",
    "pantalla_grande": "Pantalla grande", "baile_pausa": "Pausar el baile",
    "ajustes": "Ajustes", "chat": "Chat", "expresiones": "Expresiones", "bailar": "Bailar",
    "alarma": "Alarma", "tamano": "Tamaño", "bajar": "Bajar", "esquina": "Llevar a la esquina",
    "captura": "Captura", "liberar_memoria": "Liberar memoria", "modo_juego_forzar": "Modo juego",
    "salir": "Salir",
}
_RADIAL_RESPALDO = ("ajustes", "chat", "comentar", "expresiones", "bailar", "alarma", "voz", "dormir",
                    "tamano", "bajar", "mascota", "fantasma", "llamada", "esquina", "captura",
                    "liberar_memoria", "modo_juego_forzar", "pantalla_grande", "mostrar_lune", "salir")
_APP = re.compile(r"[\w .\-()]{1,80}")


# ── Catálogo y validación (con respaldo si faltan los módulos de otros cortes) ──
def _acciones_ui():
    try:
        from nucleo import acciones_ui
        return acciones_ui
    except Exception:
        return None


def etiqueta(id_: str) -> str:
    """Texto de una acción: el del catálogo común si existe; si no, el de aquí."""
    au = _acciones_ui()
    acc = getattr(au, "ACCIONES", {}).get(id_) if au else None
    texto = getattr(acc, "etiqueta", "") if acc is not None else ""
    return str(texto or _ETIQUETAS.get(id_, id_))


def candidatos_radial() -> List[str]:
    """Ids que pueden ir en el menú radial (los del catálogo con uso «radial»)."""
    au = _acciones_ui()
    acciones = getattr(au, "ACCIONES", None) if au else None
    if isinstance(acciones, dict) and acciones:
        return [i for i, a in acciones.items() if "radial" in (getattr(a, "usos", None) or ("radial",))]
    return list(_RADIAL_RESPALDO)


def validar_radial(ids: Sequence[Any]) -> List[str]:
    """Hasta 10 ids conocidos, sin repetir, en orden."""
    au = _acciones_ui()
    validar = getattr(au, "validar_lista", None) if au else None
    maximo = int(getattr(au, "MAX_RADIAL", MAX_RADIAL) or MAX_RADIAL) if au else MAX_RADIAL
    if callable(validar):
        for kw in ({"maximo": maximo, "uso": "radial"}, {"maximo": maximo}):
            try:
                return list(validar(list(ids), **kw))[:maximo]
            except TypeError:
                continue
            except Exception:
                break
    conocidos, res = set(candidatos_radial()), []
    for i in ids:
        if isinstance(i, str) and i in conocidos and i not in res:
            res.append(i)
    return res[:maximo]


def normalizar_app(nombre: Any) -> Optional[str]:
    """«C:\\Juegos\\Game.EXE» → «game.exe»; None si no es un nombre válido.
    Usa servicios.modo_juego.normalizar_app si existe (una sola regla)."""
    try:
        from servicios.modo_juego import normalizar_app as oficial
    except Exception:
        oficial = None
    texto = str(nombre or "").strip().strip('"').strip()
    if "\\" in texto or "/" in texto:
        texto = PureWindowsPath(texto).name           # pegaron una ruta: solo el .exe
    if oficial is not None:
        try:
            return oficial(texto)
        except Exception:
            return None
    texto = texto.lower()
    return texto if _APP.fullmatch(texto) else None


# ── Tecla de Qt → combo de atajos_globales («Detectar») ─────────────────────────
_TECLAS_QT = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab", Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown",
    Qt.Key.Key_Left: "left", Qt.Key.Key_Up: "up", Qt.Key.Key_Right: "right", Qt.Key.Key_Down: "down",
    Qt.Key.Key_Pause: "pause", Qt.Key.Key_Print: "printscreen",
    Qt.Key.Key_Period: "period", Qt.Key.Key_Comma: "comma", Qt.Key.Key_Minus: "minus",
    Qt.Key.Key_Plus: "plus",
}
_TECLAS_NUMPAD = {
    Qt.Key.Key_Asterisk: "multiply", Qt.Key.Key_Plus: "add", Qt.Key.Key_Minus: "subtract",
    Qt.Key.Key_Period: "decimal", Qt.Key.Key_Comma: "decimal", Qt.Key.Key_Slash: "divide",
    Qt.Key.Key_Enter: "enter",
}
_MODS_ATAJO = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
               | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier).value
_SOLO_MODIFICADOR = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                     Qt.Key.Key_AltGr, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_CapsLock}


def _tecla(key: int, numpad: bool, vk: int) -> Optional[str]:
    k = int(key)
    if numpad:
        if int(Qt.Key.Key_0) <= k <= int(Qt.Key.Key_9):
            return f"numpad{k - int(Qt.Key.Key_0)}"
        for q, nombre in _TECLAS_NUMPAD.items():
            if k == int(q):
                return nombre
    if int(Qt.Key.Key_A) <= k <= int(Qt.Key.Key_Z):
        return chr(ord("a") + k - int(Qt.Key.Key_A))
    if int(Qt.Key.Key_0) <= k <= int(Qt.Key.Key_9):
        return str(k - int(Qt.Key.Key_0))
    if int(Qt.Key.Key_F1) <= k <= int(Qt.Key.Key_F24):
        return f"f{k - int(Qt.Key.Key_F1) + 1}"
    for q, nombre in _TECLAS_QT.items():
        if k == int(q):
            return nombre
    # Con Shift, «1» llega como «!» (y depende del teclado): la tecla virtual manda.
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x70 + 1}"
    return None


def combo_de_tecla(key: int, mods: Any, vk: int = 0) -> Optional[str]:
    """Combo normalizado («ctrl+alt+shift+l») de una pulsación de Qt, o None si
    solo se pulsó un modificador o la tecla no sirve para atajos."""
    try:
        if Qt.Key(int(key)) in _SOLO_MODIFICADOR:
            return None
    except ValueError:
        pass
    m = Qt.KeyboardModifier(int(getattr(mods, "value", mods) or 0))
    nombre = _tecla(key, bool(m & Qt.KeyboardModifier.KeypadModifier), int(vk or 0))
    if not nombre:
        return None
    partes = [n for flag, n in ((Qt.KeyboardModifier.ControlModifier, "ctrl"),
                                (Qt.KeyboardModifier.AltModifier, "alt"),
                                (Qt.KeyboardModifier.ShiftModifier, "shift"),
                                (Qt.KeyboardModifier.MetaModifier, "win")) if m & flag]
    try:
        return ag.normalizar("+".join(partes + [nombre]))
    except ValueError:
        return None


# ── El panel ───────────────────────────────────────────────────────────────────
class PanelEscritorioNativo(QWidget):
    """Tema, modo juego, rendimiento, atajos y menú radial para la nativa.

    `config`: nucleo.config.Config (o un doble con .config/.save o get/set).
    `atajos`: GestorAtajosQt opcional (capturando() al detectar; estado() para
    enseñar conflictos y atajos aún no disponibles; su señal `cambio` refresca).
    `apps_visibles`: fn() → [exe] para «De las abiertas…» (por defecto
    servicios.modo_juego.apps_con_ventana si existe). `liberar_memoria`: fn() →
    (MB antes, MB después) para el botón (sin él, no hay botón).
    """

    cambiado = pyqtSignal(str)

    def __init__(self, config: Any = None, parent: Optional[QWidget] = None, *,
                 atajos: Any = None,
                 apps_visibles: Optional[Callable[[], Sequence[str]]] = None,
                 liberar_memoria: Optional[Callable[[], Any]] = None,
                 retardo_ms: int = ESPERA_GUARDADO_MS):
        super().__init__(parent)
        self.config = config
        self.atajos = atajos
        self._apps_visibles = apps_visibles if apps_visibles is not None else self._apps_por_defecto()
        self._liberar = liberar_memoria
        self._pendientes: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._cargando = False
        self._combos: Dict[str, str] = {}          # último combo válido por id de atajo
        self._errores: Dict[str, str] = {}          # error local (no guardado) por id
        self._avisos: Dict[str, str] = {}
        self._externo: Dict[str, Dict[str, Any]] = {}   # estado() del gestor de atajos por id
        self.filas_atajo: Dict[str, Dict[str, QWidget]] = {}
        self._captura: Optional[str] = None
        self._captura_previo = ""

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(retardo_ms)))
        self._timer.timeout.connect(self.guardar_ya)
        self._timer_captura = QTimer(self)
        self._timer_captura.setSingleShot(True)
        self._timer_captura.setInterval(CAPTURA_MS)
        self._timer_captura.timeout.connect(self.cancelar_captura)

        # Lo último escrito por apartado: {seccion: {(sección, clave): valor}} (quien
        # aplica `cambiado` mira aquí qué cambió de verdad).
        self.ultimo_guardado: Dict[str, Dict[Tuple[str, str], Any]] = {}
        self._atajos_conectado = None
        # Servicios del corte 4 enlazados (enlazar_servicios): el ControlTema y las
        # señales que avisan de cambios hechos desde la bandeja, el radial o un atajo.
        self._servicios = None
        self._tema_ctl = None
        self._conexiones: List[Tuple[Any, Callable]] = []

        self._construir()
        self.recargar()
        self._conectar_atajos(atajos)

    def _conectar_atajos(self, atajos: Any) -> None:
        senal = getattr(atajos, "cambio", None)
        if senal is not None and hasattr(senal, "connect"):
            try:
                senal.connect(self._al_cambio_atajos)
                self._atajos_conectado = senal
            except Exception:
                pass

    def _al_cambio_atajos(self, *_: Any) -> None:
        self.refrescar_estado_atajos()

    def set_atajos(self, atajos: Any) -> None:
        """El gestor de atajos llega después de construir el panel (la nativa monta
        los servicios del corte 4 en iniciar_servicios, tras construir Ajustes)."""
        viejo, self._atajos_conectado = self._atajos_conectado, None
        if viejo is not None:
            try:
                viejo.disconnect(self._al_cambio_atajos)
            except (TypeError, RuntimeError):
                pass
        self.atajos = atajos
        self._conectar_atajos(atajos)
        self.refrescar_estado_atajos()

    # ── Cambios hechos fuera (bandeja, radial, atajos) ───────────────────────────
    def enlazar_servicios(self, servicios: Any) -> None:
        """Los servicios del corte 4 (la nativa los monta tras construir Ajustes): el
        tema cambiado desde la bandeja, el radial o un atajo (ControlTema.cambio) y las
        claves que escriben sus acciones (ServiciosCorte4.config_cambio: siempre encima,
        barra de tareas) se ven aquí al momento. Se suelta solo al desmontarlos."""
        self._soltar_servicios()
        if servicios is None:
            return
        self._servicios = servicios
        self._tema_ctl = getattr(servicios, "tema", None)
        for senal, slot in ((getattr(self._tema_ctl, "cambio", None), self._al_tema_externo),
                            (getattr(servicios, "config_cambio", None), self._al_config_externa)):
            if senal is None or not hasattr(senal, "connect"):
                continue
            try:
                senal.connect(slot)
                self._conexiones.append((senal, slot))
            except (TypeError, RuntimeError):
                pass
        deshacer = getattr(servicios, "_deshacer", None)
        if isinstance(deshacer, list):
            deshacer.append(lambda s=servicios: self._soltar_servicios(s))
        self._al_tema_externo()

    def _soltar_servicios(self, solo: Any = None) -> None:
        """Desconecta lo de enlazar_servicios (`solo`: únicamente si son esos)."""
        if solo is not None and solo is not self._servicios:
            return
        conexiones, self._conexiones = self._conexiones, []
        for senal, slot in conexiones:
            try:
                senal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._servicios = None
        self._tema_ctl = None

    def _al_tema_externo(self, *_: Any) -> None:
        """ControlTema cambió lo que se ve (Tema ▸ de la bandeja, un atajo… o nuestro
        propio guardado): los controles del tema, con lo guardado. Si aquí hay un cambio
        sin escribir, manda el tuyo (se escribe en ≤ 300 ms, solo sus claves)."""
        if self._pendientes.get("tema"):
            return
        self._cargar_tema(self._tema_guardado())

    def _al_config_externa(self, seccion: str, clave: str) -> None:
        """Una acción escribió (sección, clave): su casilla de Rendimiento, releída."""
        chk = {("avatar", "siempre_encima"): self.chk_encima,
               ("interfaz", "en_barra_tareas"): self.chk_barra}.get((str(seccion), str(clave)))
        if chk is None or (seccion, clave) in self._pendientes.get("rendimiento", {}):
            return
        previo, self._cargando = self._cargando, True
        try:
            chk.setChecked(bool(self._leer(seccion, clave)))
        finally:
            self._cargando = previo

    def _tema_guardado(self) -> Dict[str, Any]:
        """La sección `tema` guardada: la del ControlTema enlazado (lo que tendrá
        config.json en ≤ 400 ms si la bandeja acaba de cambiarlo) o la de config."""
        f = getattr(self._tema_ctl, "guardado", None)
        if callable(f):
            try:
                d = f()
                if isinstance(d, dict) and d:
                    return tema.normalizar(d)
            except Exception:
                pass
        return tema.normalizar({k: self._leer("tema", k) for k in tema.DEFECTO})

    # ── Config ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _defecto(seccion: str, clave: str, respaldo: Any = None) -> Any:
        try:
            from nucleo.config import Config
            return copy.deepcopy(Config.DEFAULT_CONFIG.get(seccion, {}).get(clave, respaldo))
        except Exception:
            return respaldo

    def _leer(self, seccion: str, clave: str) -> Any:
        defecto = self._defecto(seccion, clave)
        cfg = self.config
        if cfg is None:
            return defecto
        try:
            datos = getattr(cfg, "config", None)
            if isinstance(datos, dict):
                v = datos.get(seccion, {}).get(clave, defecto)
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
        """¿Hay cambios sin escribir todavía?"""
        return any(self._pendientes.values())

    def guardar_ya(self) -> List[str]:
        """Escribe ya lo pendiente (una sola escritura) y emite `cambiado` por
        apartado. → apartados escritos."""
        self._timer.stop()
        pend = {s: c for s, c in self._pendientes.items() if c}
        self._pendientes = {}
        if not pend:
            return []
        todo: Dict[Tuple[str, str], Any] = {}
        for s in SECCIONES:
            todo.update(pend.get(s, {}))
        if "tema" in pend:
            # Lo que el ControlTema tenga sin escribir (la bandeja hace < 400 ms), antes:
            # si no, su guardado diferido pisaría luego las claves que escribimos aquí.
            f = getattr(self._tema_ctl, "guardar_ya", None)
            if callable(f):
                try:
                    f()
                except Exception:
                    pass
        if not escribir_claves(self.config, todo):
            self._estado(self.estado_general, "No pude guardar en config.json.", error=True)
            return []
        hechas = [s for s in SECCIONES if s in pend]
        self.ultimo_guardado = {s: dict(pend[s]) for s in hechas}
        for s in hechas:
            self.cambiado.emit(s)
        if "tema" in hechas:
            self._pintar_aviso_tema()
        return hechas

    def hideEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        self.cancelar_captura()
        self.guardar_ya()
        super().hideEvent(ev)

    def showEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        """Al enseñarse relee config.json: con Ajustes cerrado, la bandeja, el radial
        o un atajo pudieron cambiar el tema, siempre encima o la barra de tareas (si
        no, el siguiente guardado de aquí devolvería lo viejo)."""
        super().showEvent(ev)
        self.guardar_ya()
        self.recargar()

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
        lbl.setMinimumWidth(170)
        lbl.setStyleSheet(f"color:{COLORS['text']};border:none;background:transparent;")
        fila.addWidget(lbl)
        fila.addWidget(widget, 1 if isinstance(widget, (QSlider, QComboBox, QLineEdit)) else 0)
        if extra is not None:
            fila.addWidget(extra)
        if not isinstance(widget, (QSlider, QComboBox, QLineEdit)):
            fila.addStretch(1)
        return fila

    @staticmethod
    def _estado(lbl: QLabel, texto: str, error: bool = False, aviso: bool = False) -> None:
        color = COLORS["error"] if error else COLORS["warning"] if aviso else COLORS["text_muted"]
        lbl.setText(texto)
        lbl.setStyleSheet(f"color:{color};border:none;background:transparent;")

    # ── Construcción ─────────────────────────────────────────────────────────────
    def _construir(self) -> None:
        self.setObjectName("escritorioPanel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)
        self._construir_tema(raiz)
        self._construir_juego(raiz)
        self._construir_rendimiento(raiz)
        self._construir_atajos(raiz)
        self._construir_radial(raiz)
        self.estado_general = self._texto("", tenue=True)
        raiz.addWidget(self.estado_general)

    def _construir_tema(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("TEMA DE COLOR"))
        caja, fl = self._caja("temaCaja")
        self.combo_preset = self._combo()
        for pid in tema.PRESETS:
            self.combo_preset.addItem(tema.ETIQUETAS.get(pid, pid), pid)
        self.combo_preset.addItem(tema.ETIQUETAS[tema.PERSONALIZADO], tema.PERSONALIZADO)
        self.combo_preset.currentIndexChanged.connect(self._al_preset)
        fl.addLayout(self._fila("Preset", self.combo_preset))

        self.slider_tono = self._slider(0, 359)
        self.valor_tono = self._texto("0°", tenue=True)
        self.valor_tono.setFixedWidth(46)
        self.slider_tono.valueChanged.connect(self._al_tono)
        fl.addLayout(self._fila("Tono", self.slider_tono, self.valor_tono))

        self.slider_sat = self._slider(int(tema.SAT_MIN * 100), int(tema.SAT_MAX * 100))
        self.valor_sat = self._texto("100 %", tenue=True)
        self.valor_sat.setFixedWidth(46)
        self.slider_sat.valueChanged.connect(self._al_sat)
        fl.addLayout(self._fila("Saturación", self.slider_sat, self.valor_sat))

        self.chk_pop = self._check("Teñir también el amarillo", "Con Magenta el amarillo acabaría turquesa: "
                                   "por eso va aparte.")
        self.chk_pop.toggled.connect(lambda *_: self._tema_cambio("tenir_pop"))
        self.chk_fondo = self._check("Teñir también los fondos")
        self.chk_fondo.toggled.connect(lambda *_: self._tema_cambio("tenir_fondo"))
        fl.addWidget(self.chk_pop)
        fl.addWidget(self.chk_fondo)

        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.muestras: Dict[str, QLabel] = {}
        for tok in (*tema.GRUPOS["senal"], "yellow-500", "ink-800"):
            m = QLabel()
            m.setFixedSize(18, 18)
            m.setToolTip(tok)
            self.muestras[tok] = m
            fila.addWidget(m)
        fila.addStretch(1)
        self.btn_tema_restablecer = self._boton("RESTABLECER")
        self.btn_tema_restablecer.clicked.connect(self.restablecer_tema)
        fila.addWidget(self.btn_tema_restablecer)
        fl.addLayout(fila)

        self.aviso_tema = self._texto("")
        fl.addWidget(self.aviso_tema)
        raiz.addWidget(caja)

    def _construir_juego(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("MODO JUEGO"))
        caja, fl = self._caja("juegoCaja")
        self.chk_juego = self._check("Detectar juegos", "Juegos a pantalla completa o sin bordes, "
                                     "los de la lista y los de las carpetas de juegos.")
        self.chk_juego.toggled.connect(lambda v: self._poner("juego", "juego", "activo", bool(v)))
        fl.addWidget(self.chk_juego)
        self.combo_accion = self._combo()
        for clave, texto in ACCIONES_JUEGO:
            self.combo_accion.addItem(texto, clave)
        self.combo_accion.currentIndexChanged.connect(
            lambda *_: self._poner("juego", "juego", "accion", self.combo_accion.currentData()))
        fl.addLayout(self._fila("Con un juego delante", self.combo_accion))
        self.spin_juego_fps = self._spin(0, 60, " fps")
        self.spin_juego_fps.setToolTip("0 = la mascota se pausa durante la partida.")
        self.spin_juego_fps.valueChanged.connect(lambda v: self._poner("juego", "juego", "fps", int(v)))
        fl.addLayout(self._fila("FPS de la mascota en juego", self.spin_juego_fps))
        self.chk_juego_opciones: Dict[str, QCheckBox] = {}
        for clave, texto in (("incluir_videos", "Un vídeo a pantalla completa también cuenta"),
                             ("rutas_juego", "Contar lo que se abre desde Steam, Epic, Riot, Xbox o GOG"),
                             ("prioridad_baja", "Bajar la prioridad de Lune"),
                             ("recortar_ram", "Recortar la RAM de Lune al entrar"),
                             ("silenciar", "Callar la voz y los efectos")):
            c = self._check(texto)
            c.toggled.connect(lambda v, k=clave: self._poner("juego", "juego", k, bool(v)))
            self.chk_juego_opciones[clave] = c
            fl.addWidget(c)

        fl.addWidget(self._texto("Programas que siempre cuentan como juego (.exe):", tenue=True))
        self.lista_apps = QListWidget()
        self.lista_apps.setFixedHeight(96)
        self.lista_apps.setStyleSheet(f"QListWidget{{background:{COLORS['surface2']};border:1px solid "
                                      f"{COLORS['border']};color:{COLORS['text']};}}"
                                      f"QListWidget::item:selected{{background:{COLORS['surface3']};"
                                      f"color:{COLORS['accent']};}}")
        fl.addWidget(self.lista_apps)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.entrada_app = self._linea()
        self.entrada_app.setPlaceholderText("juego.exe")
        self.entrada_app.returnPressed.connect(self._anadir_app_escrita)
        self.btn_app_anadir = self._boton("AÑADIR", principal=True)
        self.btn_app_anadir.clicked.connect(self._anadir_app_escrita)
        self.btn_app_quitar = self._boton("QUITAR")
        self.btn_app_quitar.clicked.connect(self.quitar_app)
        self.btn_app_abiertas = self._boton("DE LAS ABIERTAS…")
        self.btn_app_abiertas.setToolTip("Elegir entre los programas con ventana abiertos ahora.")
        self.btn_app_abiertas.clicked.connect(self._menu_abiertas)
        self.btn_app_abiertas.setVisible(self._apps_visibles is not None)
        fila.addWidget(self.entrada_app, 1)
        fila.addWidget(self.btn_app_anadir)
        fila.addWidget(self.btn_app_quitar)
        fila.addWidget(self.btn_app_abiertas)
        fl.addLayout(fila)
        self.estado_juego = self._texto("", tenue=True)
        fl.addWidget(self.estado_juego)
        raiz.addWidget(caja)

    def _construir_rendimiento(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("RENDIMIENTO"))
        caja, fl = self._caja("rendimientoCaja")
        self.spin_fps_max = self._spin(15, 144, " fps")
        self.spin_fps_max.setToolTip("En reposo la mascota baja sola a 30 como mucho.")
        self.spin_fps_max.valueChanged.connect(
            lambda v: self._poner("rendimiento", "avatar", "fps_max", int(v)))
        fl.addLayout(self._fila("FPS máximos de la mascota", self.spin_fps_max))
        self.chk_encima = self._check("La mascota siempre encima de las ventanas")
        self.chk_encima.toggled.connect(
            lambda v: self._poner("rendimiento", "avatar", "siempre_encima", bool(v)))
        self.chk_recorte = self._check("Recortar la RAM de Lune cada 10 minutos",
                                       "Libera memoria que Lune no está usando (solo la suya).")
        self.chk_recorte.toggled.connect(
            lambda v: self._poner("rendimiento", "sistema", "recorte_ram_auto", bool(v)))
        self.chk_barra = self._check("Mostrar Lune en la barra de tareas")
        self.chk_barra.toggled.connect(
            lambda v: self._poner("rendimiento", "interfaz", "en_barra_tareas", bool(v)))
        for c in (self.chk_encima, self.chk_recorte, self.chk_barra):
            fl.addWidget(c)
        fila = QHBoxLayout()
        self.btn_liberar = self._boton("LIBERAR MEMORIA AHORA")
        self.btn_liberar.clicked.connect(self.liberar_memoria)
        self.btn_liberar.setVisible(self._liberar is not None)
        fila.addWidget(self.btn_liberar)
        fila.addStretch(1)
        fl.addLayout(fila)
        self.estado_rendimiento = self._texto("", tenue=True)
        fl.addWidget(self.estado_rendimiento)
        raiz.addWidget(caja)

    def _construir_atajos(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("ATAJOS DE TECLADO"))
        caja, fl = self._caja("atajosCaja")
        fl.addWidget(self._texto("Funcionan aunque Lune no tenga el foco (RegisterHotKey, sin leer el resto "
                                 "del teclado). Por defecto llevan Ctrl+Alt+Shift: con Ctrl+Alt solo, AltGr "
                                 "se comería la @ o el €.", tenue=True))
        self.chk_atajos = self._check("Atajos globales activos")
        self.chk_atajos.toggled.connect(lambda v: self._poner("atajos", "atajos", "activo", bool(v)))
        self.chk_atajos_juego = self._check("Pausarlos en modo juego (salvo «Mostrar Lune»)")
        self.chk_atajos_juego.toggled.connect(
            lambda v: self._poner("atajos", "atajos", "pausar_en_juegos", bool(v)))
        self.chk_atajos_sonido = self._check("Sonar al usar un atajo")
        self.chk_atajos_sonido.toggled.connect(lambda v: self._poner("atajos", "atajos", "sonido", bool(v)))
        for c in (self.chk_atajos, self.chk_atajos_juego, self.chk_atajos_sonido):
            fl.addWidget(c)
        self._caja_filas_atajo = QVBoxLayout()
        self._caja_filas_atajo.setSpacing(6)
        fl.addLayout(self._caja_filas_atajo)
        fila = QHBoxLayout()
        fila.addStretch(1)
        self.btn_atajos_restablecer = self._boton("RESTABLECER ATAJOS")
        self.btn_atajos_restablecer.clicked.connect(self.restablecer_atajos)
        fila.addWidget(self.btn_atajos_restablecer)
        fl.addLayout(fila)
        raiz.addWidget(caja)

    def _fila_atajo(self, id_: str) -> Dict[str, QWidget]:
        cont = QWidget()
        col = QVBoxLayout(cont)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        lbl = QLabel(etiqueta(id_))
        lbl.setMinimumWidth(170)
        lbl.setStyleSheet(f"color:{COLORS['text']};border:none;background:transparent;")
        edit = self._linea()
        edit.setFont(QFont(FONT_MONO, 9))
        edit.setPlaceholderText("sin atajo")
        edit.editingFinished.connect(lambda i=id_: self._al_editar_atajo(i))
        btn = self._boton("DETECTAR")
        btn.clicked.connect(lambda _=False, i=id_: self.detectar(i))
        fila.addWidget(lbl)
        fila.addWidget(edit, 1)
        fila.addWidget(btn)
        col.addLayout(fila)
        estado = self._texto("", tenue=True)
        estado.setVisible(False)
        col.addWidget(estado)
        self._caja_filas_atajo.addWidget(cont)
        return {"contenedor": cont, "etiqueta": lbl, "edit": edit, "boton": btn, "estado": estado}

    def _construir_radial(self, raiz: QVBoxLayout) -> None:
        raiz.addWidget(self._titulo("MENÚ RADIAL DE LA MASCOTA"))
        caja, fl = self._caja("radialCaja")
        fl.addWidget(self._texto("Clic derecho sobre la mascota (o el atajo del menú radial). Hasta 10 "
                                 "botones, en este orden empezando arriba y en el sentido del reloj.",
                                 tenue=True))
        self.lista_radial = QListWidget()
        self.lista_radial.setFixedHeight(150)
        self.lista_radial.setStyleSheet(self.lista_apps.styleSheet())
        fl.addWidget(self.lista_radial)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.combo_radial = self._combo()
        self.btn_radial_anadir = self._boton("AÑADIR", principal=True)
        self.btn_radial_anadir.clicked.connect(self.anadir_radial)
        self.btn_radial_subir = self._boton("SUBIR")
        self.btn_radial_subir.clicked.connect(lambda: self.mover_radial(-1))
        self.btn_radial_bajar = self._boton("BAJAR")
        self.btn_radial_bajar.clicked.connect(lambda: self.mover_radial(1))
        self.btn_radial_quitar = self._boton("QUITAR")
        self.btn_radial_quitar.clicked.connect(self.quitar_radial)
        fila.addWidget(self.combo_radial, 1)
        for b in (self.btn_radial_anadir, self.btn_radial_subir, self.btn_radial_bajar, self.btn_radial_quitar):
            fila.addWidget(b)
        fl.addLayout(fila)
        self.chk_menu_sonidos = self._check("Sonidos al abrir, cerrar y pulsar")
        self.chk_menu_sonidos.toggled.connect(lambda v: self._poner("radial", "menu", "sonidos", bool(v)))
        fl.addWidget(self.chk_menu_sonidos)
        self.slider_menu_vol = self._slider(0, 100)
        self.valor_menu_vol = self._texto("60 %", tenue=True)
        self.valor_menu_vol.setFixedWidth(46)
        self.slider_menu_vol.valueChanged.connect(self._al_volumen_menu)
        fl.addLayout(self._fila("Volumen de los menús", self.slider_menu_vol, self.valor_menu_vol))
        self.estado_radial = self._texto("", tenue=True)
        fl.addWidget(self.estado_radial)
        raiz.addWidget(caja)

    # ── Recarga ──────────────────────────────────────────────────────────────────
    def recargar(self) -> None:
        """Vuelve a leer config.json en los controles (sin guardar nada)."""
        self.cancelar_captura()
        self._cargando = True
        try:
            self._cargar_tema(self._tema_guardado())
            self.chk_juego.setChecked(bool(self._leer("juego", "activo")))
            i = self.combo_accion.findData(str(self._leer("juego", "accion") or "ocultar"))
            self.combo_accion.setCurrentIndex(max(0, i))
            self.spin_juego_fps.setValue(self._entero(self._leer("juego", "fps"), 0))
            for clave, c in self.chk_juego_opciones.items():
                c.setChecked(bool(self._leer("juego", clave)))
            self.lista_apps.clear()
            for app in self._apps_config():
                self.lista_apps.addItem(app)
            self.spin_fps_max.setValue(self._entero(self._leer("avatar", "fps_max"), 60))
            self.chk_encima.setChecked(bool(self._leer("avatar", "siempre_encima")))
            self.chk_recorte.setChecked(bool(self._leer("sistema", "recorte_ram_auto")))
            self.chk_barra.setChecked(bool(self._leer("interfaz", "en_barra_tareas")))
            self.chk_atajos.setChecked(bool(self._leer("atajos", "activo")))
            self.chk_atajos_juego.setChecked(bool(self._leer("atajos", "pausar_en_juegos")))
            self.chk_atajos_sonido.setChecked(bool(self._leer("atajos", "sonido")))
            self._cargar_atajos(self._leer("atajos", "lista"))
            self._cargar_radial(self._leer("menu_radial", "principal"))
            self.chk_menu_sonidos.setChecked(bool(self._leer("menu", "sonidos")))
            vol = self._leer("menu", "volumen")
            self.slider_menu_vol.setValue(int(round(max(0.0, min(1.0, self._flotante(vol, 0.6))) * 100)))
            self.valor_menu_vol.setText(f"{self.slider_menu_vol.value()} %")
        finally:
            self._cargando = False
        self.refrescar_estado_atajos()

    @staticmethod
    def _entero(v: Any, defecto: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return defecto

    @staticmethod
    def _flotante(v: Any, defecto: float) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return defecto

    # ── Tema ─────────────────────────────────────────────────────────────────────
    def _cargar_tema(self, n: Dict[str, Any]) -> None:
        previo, self._cargando = self._cargando, True
        try:
            self.combo_preset.setCurrentIndex(max(0, self.combo_preset.findData(n["preset"])))
            self.slider_tono.setValue(int(round(n["hue"])) % 360)
            self.valor_tono.setText(f"{self.slider_tono.value()}°")
            self.slider_sat.setValue(int(round(n["saturacion"] * 100)))
            self.valor_sat.setText(f"{self.slider_sat.value()} %")
            self.chk_pop.setChecked(bool(n["tenir_pop"]))
            self.chk_fondo.setChecked(bool(n["tenir_fondo"]))
        finally:
            self._cargando = previo
        self._pintar_muestras()
        self._pintar_aviso_tema()

    def tema_ui(self) -> Dict[str, Any]:
        """La sección `tema` que dicen ahora los controles (normalizada)."""
        return tema.normalizar({
            "preset": self.combo_preset.currentData(),
            "hue": self.slider_tono.value(),
            "saturacion": self.slider_sat.value() / 100.0,
            "tenir_pop": self.chk_pop.isChecked(),
            "tenir_fondo": self.chk_fondo.isChecked(),
        })

    def _al_preset(self, *_: Any) -> None:
        pid = self.combo_preset.currentData()
        if pid in tema.PRESETS:
            previo, self._cargando = self._cargando, True
            try:
                self.slider_tono.setValue(int(round(tema.PRESETS[pid] * 360)) % 360)
                self.valor_tono.setText(f"{self.slider_tono.value()}°")
            finally:
                self._cargando = previo
        self._tema_cambio("preset", "hue")

    def _al_tono(self, valor: int) -> None:
        self.valor_tono.setText(f"{valor}°")
        if self._cargando:
            return
        pid = self.combo_preset.currentData()
        if pid in tema.PRESETS and valor != int(round(tema.PRESETS[pid] * 360)) % 360:
            self._cargando = True                       # mover el tono = personalizado
            try:
                self.combo_preset.setCurrentIndex(self.combo_preset.findData(tema.PERSONALIZADO))
            finally:
                self._cargando = False
        self._tema_cambio("preset", "hue")

    def _al_sat(self, valor: int) -> None:
        self.valor_sat.setText(f"{valor} %")
        self._tema_cambio("saturacion")

    def _tema_cambio(self, *claves: str) -> None:
        """Un control del tema cambió: se escriben SOLO sus claves (`claves`; sin
        ninguna, las cinco). Las demás pudo cambiarlas la bandeja, el radial o un atajo
        con Ajustes abierto: reescribirlas desde estos controles las devolvería."""
        self._pintar_muestras()
        if self._cargando:
            return
        ui = self.tema_ui()
        for clave in (claves or tuple(ui)):
            self._poner("tema", "tema", clave, ui[clave])
        self._pintar_aviso_tema()

    def restablecer_tema(self) -> None:
        """Cian, 100 %, sin teñir amarillo ni fondos (se guarda)."""
        self._cargar_tema(tema.normalizar(tema.DEFECTO))
        for clave, valor in tema.normalizar(tema.DEFECTO).items():
            self._poner("tema", "tema", clave, valor)
        self._pintar_aviso_tema()

    def _pintar_muestras(self) -> None:
        pal = tema.paleta(self.tema_ui())
        for tok, m in self.muestras.items():
            m.setStyleSheet(f"background:{pal[tok]};border:1px solid {COLORS['border']};")

    def _pintar_aviso_tema(self) -> None:
        """Aviso de reinicio: en amarillo si la ventana nativa aún no lleva este tema."""
        nativo = tema.colores_nativos(tema.paleta(self.tema_ui()))
        distinto = any(COLORS.get(k) != v for k, v in nativo.items())
        texto = ("La mascota, la bandeja y el menú radial cambian al momento; esta ventana "
                 "se recolorea al reiniciar Lune.")
        if distinto:
            texto = "Reinicia Lune para ver el nuevo color aquí. " + texto
        self._estado(self.aviso_tema, texto, aviso=distinto)

    # ── Modo juego ───────────────────────────────────────────────────────────────
    def _apps_config(self) -> List[str]:
        res: List[str] = []
        v = self._leer("juego", "apps")
        for a in v if isinstance(v, list) else []:
            n = normalizar_app(a)
            if n and n not in res:
                res.append(n)
        return res[:MAX_APPS]

    def apps(self) -> List[str]:
        return [self.lista_apps.item(i).text() for i in range(self.lista_apps.count())]

    def _anadir_app_escrita(self) -> None:
        if self.anadir_app(self.entrada_app.text()):
            self.entrada_app.clear()

    def anadir_app(self, nombre: Any) -> bool:
        """Añade un .exe a juego.apps (normalizado, sin repetir). True si entró."""
        n = normalizar_app(nombre)
        if not n:
            self._estado(self.estado_juego, f"«{str(nombre or '').strip()[:60]}» no es un nombre de programa "
                                            "válido (por ejemplo juego.exe).", error=True)
            return False
        actuales = self.apps()
        if n in actuales:
            self._estado(self.estado_juego, f"«{n}» ya está en la lista.")
            return False
        if len(actuales) >= MAX_APPS:
            self._estado(self.estado_juego, f"Como mucho {MAX_APPS} programas.", error=True)
            return False
        self.lista_apps.addItem(n)
        self._estado(self.estado_juego, f"«{n}» cuenta como juego.")
        self._poner("juego", "juego", "apps", self.apps())
        return True

    def quitar_app(self) -> bool:
        fila = self.lista_apps.currentRow()
        if fila < 0:
            return False
        item = self.lista_apps.takeItem(fila)
        self._estado(self.estado_juego, f"«{item.text()}» ya no cuenta como juego." if item else "")
        self._poner("juego", "juego", "apps", self.apps())
        return True

    @staticmethod
    def _apps_por_defecto() -> Optional[Callable[[], Sequence[str]]]:
        try:
            from servicios.modo_juego import apps_con_ventana
        except Exception:
            return None
        return apps_con_ventana

    def apps_abiertas(self) -> List[str]:
        """Programas con ventana abiertos ahora (normalizados, sin los de la lista)."""
        if self._apps_visibles is None:
            return []
        try:
            vistas = list(self._apps_visibles() or [])
        except Exception:
            return []
        ya, res = set(self.apps()), []
        for a in vistas:
            n = normalizar_app(a)
            if n and n not in ya and n not in res:
                res.append(n)
        return sorted(res)

    def _menu_abiertas(self) -> None:
        opciones = self.apps_abiertas()
        menu = QMenu(self)
        if not opciones:
            a = menu.addAction("No hay otros programas con ventana")
            a.setEnabled(False)
        for n in opciones:
            menu.addAction(n).triggered.connect(lambda _=False, x=n: self.anadir_app(x))
        menu.exec(self.btn_app_abiertas.mapToGlobal(self.btn_app_abiertas.rect().bottomLeft()))

    # ── Rendimiento ──────────────────────────────────────────────────────────────
    def liberar_memoria(self) -> None:
        if self._liberar is None:
            return
        try:
            r = self._liberar()
        except Exception as e:
            self._estado(self.estado_rendimiento, f"No pude liberar memoria: {e}", error=True)
            return
        try:
            antes, despues = float(r[0]), float(r[1])
            texto = f"Memoria de Lune: {antes:.0f} MB → {despues:.0f} MB."
        except (TypeError, ValueError, IndexError):
            texto = "Memoria liberada."
        self._estado(self.estado_rendimiento, texto)

    # ── Atajos ───────────────────────────────────────────────────────────────────
    def _cargar_atajos(self, lista: Any) -> None:
        ids: List[str] = []
        combos: Dict[str, str] = {}
        for it in lista if isinstance(lista, list) else []:
            if isinstance(it, dict) and isinstance(it.get("id"), str) and it["id"] not in ids:
                ids.append(it["id"])
                combos[it["id"]] = str(it.get("combo") or "")
        if list(self.filas_atajo) != ids:                     # otras filas: se rehacen
            for fila in self.filas_atajo.values():
                fila["contenedor"].setParent(None)
                fila["contenedor"].deleteLater()
            self.filas_atajo = {i: self._fila_atajo(i) for i in ids}
        self._combos = {}
        self._errores.clear()
        self._avisos.clear()
        for i in ids:
            c = combos.get(i, "")
            try:
                c = ag.normalizar(c) if c else ""
            except ValueError:
                pass                                         # se enseña tal cual, con su error
            self._combos[i] = c
            self.filas_atajo[i]["edit"].setText(c)
            if c:
                err, av = ag.comprobar(c)
                if err:
                    self._errores[i] = err
                elif av:
                    self._avisos[i] = av
        self._pintar_atajos()

    def combo_atajo(self, id_: str) -> str:
        """Combo guardado (o por guardar) de un atajo ("" = sin atajo)."""
        return self._combos.get(id_, "")

    def _lista_atajos(self) -> List[Dict[str, str]]:
        return [{"id": i, "combo": self._combos.get(i, "")} for i in self.filas_atajo]

    def _al_editar_atajo(self, id_: str) -> None:
        if self._captura == id_ or id_ not in self.filas_atajo:
            return
        self.cambiar_atajo(id_, self.filas_atajo[id_]["edit"].text())

    def cambiar_atajo(self, id_: str, combo: str) -> bool:
        """Valida y guarda el combo de un atajo. Los errores (y los duplicados) no
        se guardan y se enseñan; los avisos (Ctrl+Alt sin Shift) sí se guardan."""
        if id_ not in self.filas_atajo:
            return False
        texto = str(combo or "").strip()
        edit = self.filas_atajo[id_]["edit"]
        self._errores.pop(id_, None)
        self._avisos.pop(id_, None)
        if not texto:
            normal = ""
        else:
            err, av = ag.comprobar(texto)
            if err:
                self._errores[id_] = err
                edit.setText(texto)
                self._pintar_atajos()
                return False
            normal = ag.normalizar(texto)
            otro = next((i for i, c in self._combos.items() if i != id_ and c and c == normal), None)
            if otro:
                self._errores[id_] = f"Ya lo usa «{etiqueta(otro)}»."
                edit.setText(texto)
                self._pintar_atajos()
                return False
            if av:
                self._avisos[id_] = av
        edit.setText(normal)
        cambio = self._combos.get(id_, "") != normal
        self._combos[id_] = normal
        self._pintar_atajos()
        if cambio:
            self._poner("atajos", "atajos", "lista", self._lista_atajos())
        return True

    def restablecer_atajos(self) -> None:
        """Los combos por defecto de DEFAULT_CONFIG (se guardan)."""
        defecto = self._defecto("atajos", "lista", [])
        self._cargar_atajos(defecto)
        self._poner("atajos", "atajos", "lista", self._lista_atajos())

    def refrescar_estado_atajos(self) -> None:
        """Conflictos del gestor (otra app ya lo usa…) y atajos aún sin acción."""
        estado = []
        f = getattr(self.atajos, "estado", None)
        if callable(f):
            try:
                estado = list(f() or [])
            except Exception:
                estado = []
        self._externo = {e.get("id"): e for e in estado if isinstance(e, dict)}
        self._pintar_atajos()

    def _pintar_atajos(self) -> None:
        for i, fila in self.filas_atajo.items():
            ext = self._externo.get(i) or {}
            disponible = ext.get("disponible", True) is not False
            fila["edit"].setEnabled(disponible)
            fila["boton"].setEnabled(disponible)
            fila["etiqueta"].setToolTip("" if disponible else "Llega en una versión próxima de Lune.")
            err = self._errores.get(i) or ext.get("error") or ""
            av = self._avisos.get(i) or ext.get("aviso") or ""
            lbl = fila["estado"]
            if not disponible:
                self._estado(lbl, "Aún no disponible.")
            elif err:
                self._estado(lbl, str(err), error=True)
            elif av:
                self._estado(lbl, str(av), aviso=True)
            else:
                lbl.setText("")
            lbl.setVisible(bool(lbl.text()))

    # «Detectar»: el campo captura la siguiente combinación (Esc cancela, 15 s máx.)
    def detectar(self, id_: str) -> bool:
        if id_ not in self.filas_atajo:
            return False
        self.cancelar_captura()
        fila = self.filas_atajo[id_]
        edit = fila["edit"]
        self._captura = id_
        self._captura_previo = edit.text()
        edit.setReadOnly(True)
        edit.setText("")
        edit.setPlaceholderText("Pulsa la combinación… (Esc cancela)")
        edit.installEventFilter(self)
        fila["boton"].setText("CANCELAR")
        try:
            fila["boton"].clicked.disconnect()
        except TypeError:
            pass
        fila["boton"].clicked.connect(lambda _=False: self.cancelar_captura())
        self._pausar_atajos(True)
        self._timer_captura.start()
        edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._pintar_atajos()
        return True

    @property
    def capturando(self) -> Optional[str]:
        """Id del atajo que está esperando una tecla (o None)."""
        return self._captura

    def _fin_captura(self) -> Optional[str]:
        id_ = self._captura
        if id_ is None:
            return None
        self._captura = None
        self._timer_captura.stop()
        fila = self.filas_atajo.get(id_)
        if fila is not None:
            edit = fila["edit"]
            edit.removeEventFilter(self)
            edit.setReadOnly(False)
            edit.setPlaceholderText("sin atajo")
            fila["boton"].setText("DETECTAR")
            try:
                fila["boton"].clicked.disconnect()
            except TypeError:
                pass
            fila["boton"].clicked.connect(lambda _=False, i=id_: self.detectar(i))
        self._pausar_atajos(False)
        return id_

    def cancelar_captura(self) -> None:
        id_ = self._fin_captura()
        if id_ is not None and id_ in self.filas_atajo:
            self.filas_atajo[id_]["edit"].setText(self._captura_previo)
            self._pintar_atajos()

    def capturar(self, key: int, mods: Any, vk: int = 0) -> Optional[str]:
        """Una pulsación durante «Detectar». → combo guardado, o None si aún no hay
        tecla principal (solo modificadores) o se canceló con Esc."""
        if self._captura is None:
            return None
        m = int(getattr(mods, "value", mods) or 0)
        if int(key) == int(Qt.Key.Key_Escape) and not (m & _MODS_ATAJO):
            self.cancelar_captura()
            return None
        combo = combo_de_tecla(key, mods, vk)
        if combo is None:
            return None
        id_ = self._fin_captura()
        if id_ is None or not self.cambiar_atajo(id_, combo):
            return None
        return combo

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:           # noqa: N802 (Qt)
        if self._captura is not None and obj is self.filas_atajo.get(self._captura, {}).get("edit"):
            t = ev.type()
            if t == QEvent.Type.KeyPress:
                self.capturar(ev.key(), ev.modifiers(), ev.nativeVirtualKey())
                return True
            if t in (QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride):
                return True
            if t == QEvent.Type.FocusOut:
                self.cancelar_captura()
        return super().eventFilter(obj, ev)

    def _pausar_atajos(self, on: bool) -> None:
        f = getattr(self.atajos, "capturando", None)
        if callable(f):
            try:
                f(bool(on))
            except Exception:
                pass

    # ── Menú radial ──────────────────────────────────────────────────────────────
    def _cargar_radial(self, ids: Any) -> None:
        self.lista_radial.clear()
        for i in validar_radial(ids if isinstance(ids, list) else []):
            item = QListWidgetItem(etiqueta(i))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.lista_radial.addItem(item)
        self._rellenar_combo_radial()

    def radial(self) -> List[str]:
        return [self.lista_radial.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista_radial.count())]

    def _rellenar_combo_radial(self) -> None:
        ya = set(self.radial())
        self.combo_radial.clear()
        for i in candidatos_radial():
            if i not in ya:
                self.combo_radial.addItem(etiqueta(i), i)
        lleno = len(ya) >= MAX_RADIAL
        self.btn_radial_anadir.setEnabled(not lleno and self.combo_radial.count() > 0)
        if lleno:
            self._estado(self.estado_radial, f"El menú radial ya tiene {MAX_RADIAL} botones.")

    def _guardar_radial(self) -> None:
        self._rellenar_combo_radial()
        self._poner("radial", "menu_radial", "principal", self.radial())

    def anadir_radial(self, id_: Optional[str] = None) -> bool:
        i = id_ if isinstance(id_, str) else self.combo_radial.currentData()
        actuales = self.radial()
        if not i or i in actuales or len(actuales) >= MAX_RADIAL or i not in candidatos_radial():
            return False
        item = QListWidgetItem(etiqueta(i))
        item.setData(Qt.ItemDataRole.UserRole, i)
        self.lista_radial.addItem(item)
        self.lista_radial.setCurrentRow(self.lista_radial.count() - 1)
        self._estado(self.estado_radial, "")
        self._guardar_radial()
        return True

    def quitar_radial(self) -> bool:
        fila = self.lista_radial.currentRow()
        if fila < 0:
            return False
        self.lista_radial.takeItem(fila)
        self._estado(self.estado_radial, "")
        self._guardar_radial()
        return True

    def mover_radial(self, paso: int) -> bool:
        fila = self.lista_radial.currentRow()
        destino = fila + int(paso)
        if fila < 0 or not (0 <= destino < self.lista_radial.count()):
            return False
        item = self.lista_radial.takeItem(fila)
        self.lista_radial.insertItem(destino, item)
        self.lista_radial.setCurrentRow(destino)
        self._guardar_radial()
        return True

    def _al_volumen_menu(self, valor: int) -> None:
        self.valor_menu_vol.setText(f"{valor} %")
        self._poner("radial", "menu", "volumen", round(valor / 100.0, 2))


__all__ = ("PanelEscritorioNativo", "SECCIONES", "combo_de_tecla", "normalizar_app", "etiqueta",
           "candidatos_radial", "validar_radial")
