"""
ui/vrm_panel_nativo.py — Modelos 3D (VRM) en la interfaz nativa (PyQt6).

PARA QUÉ SIRVE
--------------
La interfaz web tiene la biblioteca completa (ui_web/ui_kits/lune-desktop/extra/
vrm_biblioteca.jsx: rejilla, calibración en vivo, borrar…). La nativa
(ui/settings_panel.py) solo tenía «Sprites 2D / Avatar VRM 3D» en un combo. Este
panel le da lo imprescindible de «Custom VRM» y del seguimiento de Mate-Engine:

- Combo con los modelos válidos de modelo_vrm/ (`nucleo.vrm.listar_modelos`),
  con la miniatura que trae el propio .vrm y su ficha (versión, autor, licencia,
  quién lo usa).
- «IMPORTAR .VRM…»: copia el archivo a modelo_vrm/ (`vrm.importar_modelo`).
- «USAR CON <personaje>» / «QUITAR»: el modelo del personaje activo
  (`vrm.asignar_a_personaje`).
- Seguimiento del cursor por modelo: cabeza, torso y ojos (0–100 %), guardado en
  modelo_vrm/<modelo>.lune.json con `vrm.guardar_ajustes_modelo` (pesoCabeza,
  pesoTorso, pesoOjos). Si el modelo no trae lookAt, aviso «Este modelo no mueve
  los ojos» y el deslizador de ojos en gris. Los deslizadores esperan 250 ms
  quietos antes de escribir (no se reescribe el archivo en cada píxel).

Señal `cambiado()`: se importó, se asignó o se guardó el seguimiento. Quien lo
integra (settings_panel.py / main.py) recarga la asistente 3D o le manda
`window.luneParams(vrm.params_modelo_json(modelo, config))`.

    panel = VrmPanelNativo(config)
    panel.cambiado.connect(lambda: companion.recargar_vrm())

Sin WebEngine el panel funciona igual (solo avisa de que la asistente 3D no se
podrá ver). Estilo de ui/theme.py (COLORS).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from nucleo import personajes, vrm
from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

# Deslizadores de seguimiento: (clave de AJUSTES, etiqueta, ayuda)
SEGUIMIENTO = (
    ("pesoCabeza", "Cabeza", "Cuánto gira la cabeza hacia el cursor."),
    ("pesoTorso", "Torso", "Cuánto acompaña el torso al girar."),
    ("pesoOjos", "Ojos", "Cuánto miran los ojos al cursor."),
)
ESPERA_GUARDADO_MS = 250
TAM_MINIATURA = 72


def _cfg(config: Any, clave: str, defecto: Any = None) -> Any:
    if config is None:
        return defecto
    try:
        return config.get("avatar", clave, defecto)
    except Exception:
        return defecto


def _elegir_archivo_dialogo(parent: Optional[QWidget]) -> str:
    ruta, _ = QFileDialog.getOpenFileName(parent, "Importar modelo VRM", str(Path.home()),
                                          "Modelos VRM (*.vrm)")
    return ruta or ""


class VrmPanelNativo(QWidget):
    """Modelos VRM y seguimiento del cursor para la interfaz nativa.

    `config`: nucleo.config.Config (para los pesos globales avatar.peso_* y
    avatar.vrm_archivo); puede ser None. `elegir_archivo`: fn() → ruta o "" (por
    defecto un QFileDialog; los tests la sustituyen).
    """

    cambiado = pyqtSignal()

    def __init__(self, config: Any = None, parent: Optional[QWidget] = None, *,
                 elegir_archivo: Optional[Callable[[], str]] = None):
        super().__init__(parent)
        self.config = config
        self._elegir_archivo = elegir_archivo or (lambda: _elegir_archivo_dialogo(self))
        self._meta: Dict[str, Any] = {}
        self._pendientes: Dict[str, float] = {}
        self._pendiente_modelo = ""
        self._cargando = False
        self.sliders: Dict[str, QSlider] = {}
        self._valores: Dict[str, QLabel] = {}

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ESPERA_GUARDADO_MS)
        self._timer.timeout.connect(self.guardar_ya)

        self._construir()
        self.recargar()

    # ── Construcción ─────────────────────────────────────────────────────────────
    def _construir(self) -> None:
        self.setObjectName("vrmPanel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(10)

        titulo = QLabel("MODELOS 3D · VRM")
        titulo.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        titulo.setStyleSheet(f"color:{COLORS['accent']};border:none;letter-spacing:1px;")
        raiz.addWidget(titulo)

        self.aviso_webengine = QLabel("Sin PyQt6-WebEngine no puedo salir al escritorio en 3D; "
                                      "los modelos se guardan igual.")
        self.aviso_webengine.setWordWrap(True)
        self.aviso_webengine.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        self.aviso_webengine.setVisible(not vrm.webengine_disponible())
        raiz.addWidget(self.aviso_webengine)

        caja = QFrame()
        caja.setObjectName("vrmCaja")
        caja.setStyleSheet(f"QFrame#vrmCaja{{background:{COLORS['surface']};border:1px solid {COLORS['border']};"
                           f"border-radius:3px;}}")
        fl = QVBoxLayout(caja)
        fl.setContentsMargins(14, 14, 14, 14)
        fl.setSpacing(10)

        # Modelo + miniatura + ficha
        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.miniatura = QLabel()
        self.miniatura.setFixedSize(TAM_MINIATURA, TAM_MINIATURA)
        self.miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.miniatura.setStyleSheet(f"background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
                                     f"border-radius:3px;color:{COLORS['text_dim']};")
        fila.addWidget(self.miniatura)
        col = QVBoxLayout()
        col.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setStyleSheet(
            f"QComboBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
            f"border-radius:3px;padding:8px 12px;color:{COLORS['text']};}}"
            f"QComboBox:disabled{{color:{COLORS['text_dim']};}}"
            f"QComboBox QAbstractItemView{{background:{COLORS['surface2']};color:{COLORS['text']};"
            f"selection-background-color:{COLORS['accent']};selection-color:{COLORS['bg']};}}")
        self.combo.currentIndexChanged.connect(self._al_elegir)
        col.addWidget(self.combo)
        self.ficha = QLabel("")
        self.ficha.setWordWrap(True)
        self.ficha.setFont(QFont(FONT_MONO, 8))
        self.ficha.setStyleSheet(f"color:{COLORS['text_muted']};border:none;background:transparent;")
        col.addWidget(self.ficha)
        fila.addLayout(col, 1)
        fl.addLayout(fila)

        # Botones
        botones = QHBoxLayout()
        botones.setSpacing(8)
        self.btn_importar = self._boton("IMPORTAR .VRM…", principal=True)
        self.btn_importar.setToolTip("Copia un .vrm a la carpeta modelo_vrm/ de Lune.")
        self.btn_importar.clicked.connect(self.importar)
        self.btn_asignar = self._boton("USAR CON LUNE")
        self.btn_asignar.clicked.connect(self.asignar)
        self.btn_quitar = self._boton("QUITAR")
        self.btn_quitar.setToolTip("El personaje activo vuelve al modelo por defecto.")
        self.btn_quitar.clicked.connect(self.quitar)
        botones.addWidget(self.btn_importar)
        botones.addWidget(self.btn_asignar)
        botones.addWidget(self.btn_quitar)
        botones.addStretch(1)
        fl.addLayout(botones)

        # Seguimiento del cursor
        sub = QLabel("Seguimiento del cursor (este modelo)")
        sub.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        sub.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:4px;")
        fl.addWidget(sub)
        for clave, etiqueta, ayuda in SEGUIMIENTO:
            fl.addLayout(self._fila_slider(clave, etiqueta, ayuda))
        self.aviso_ojos = QLabel("Este modelo no mueve los ojos (no trae lookAt).")
        self.aviso_ojos.setWordWrap(True)
        self.aviso_ojos.setStyleSheet(f"color:{COLORS['warning']};border:none;")
        self.aviso_ojos.setVisible(False)
        fl.addWidget(self.aviso_ojos)

        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        self.estado.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(self.estado)
        raiz.addWidget(caja)

    def _boton(self, texto: str, principal: bool = False) -> QPushButton:
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(FONT_DISPLAY, 9, QFont.Weight.Bold))
        b.setFixedHeight(32)
        borde = COLORS["cyan_dark"] if principal else COLORS["border"]
        color = COLORS["accent"] if principal else COLORS["text_muted"]
        b.setStyleSheet(
            f"QPushButton{{background:{COLORS['surface2']};color:{color};border:2px solid {borde};"
            f"border-radius:3px;padding:0 12px;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:{COLORS['surface3']};color:{COLORS['accent']};border-color:{COLORS['accent']};}}"
            f"QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        return b

    def _fila_slider(self, clave: str, etiqueta: str, ayuda: str) -> QHBoxLayout:
        fila = QHBoxLayout()
        fila.setSpacing(10)
        lbl = QLabel(etiqueta)
        lbl.setFixedWidth(64)
        lbl.setToolTip(ayuda)
        lbl.setStyleSheet(f"color:{COLORS['text']};border:none;")
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setSingleStep(5)
        s.setPageStep(10)
        s.setToolTip(ayuda)
        s.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px;background:{COLORS['surface3']};border-radius:2px;}}"
            f"QSlider::sub-page:horizontal{{background:{COLORS['accent']};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{COLORS['text']};border:2px solid {COLORS['accent']};"
            f"width:10px;margin:-6px 0;border-radius:2px;}}"
            f"QSlider::sub-page:horizontal:disabled{{background:{COLORS['border']};}}"
            f"QSlider::handle:horizontal:disabled{{background:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        s.valueChanged.connect(lambda v, c=clave: self._al_mover(c, v))
        val = QLabel("100 %")
        val.setFixedWidth(46)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val.setFont(QFont(FONT_MONO, 9))
        val.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self.sliders[clave] = s
        self._valores[clave] = val
        fila.addWidget(lbl)
        fila.addWidget(s, 1)
        fila.addWidget(val)
        return fila

    # ── Datos ────────────────────────────────────────────────────────────────────
    @property
    def modelo(self) -> str:
        """Archivo del modelo elegido en el combo ("" si no hay)."""
        d = self.combo.currentData()
        return d if isinstance(d, str) else ""

    def _personaje_activo(self) -> Dict[str, Any]:
        try:
            p = personajes.get_activo()
        except Exception:
            p = {}
        return p if isinstance(p, dict) else {}

    def _modelo_de_activo(self) -> str:
        """Archivo (dentro de modelo_vrm/) que usa el personaje activo, o ""."""
        v = str(self._personaje_activo().get("vrm") or "").strip()
        r = vrm.resolver(v) if v else None
        return r.name if r is not None else ""

    def peso(self, modelo: str, clave: str) -> float:
        """Peso de seguimiento efectivo: el del modelo, si no el global de config, si no el defecto."""
        propio = vrm.ajustes_modelo(modelo).get(clave) if modelo else None
        if propio is not None:
            return float(propio)
        glob = vrm.validar_valor(clave, _cfg(self.config, vrm.PESOS_CONFIG.get(clave, ""), None))
        if glob is not None:
            return float(glob)
        return float(vrm.AJUSTES[clave]["defecto"])

    def recargar(self, elegir: str = "") -> None:
        """Vuelve a leer modelo_vrm/ y elige `elegir`, el actual, el del personaje
        activo, el de config o el primero (en ese orden)."""
        self.guardar_ya()
        previo = elegir or self.modelo
        modelos = vrm.listar_modelos()
        candidatos = [previo, self._modelo_de_activo(), Path(str(_cfg(self.config, "vrm_archivo", "") or "")).name]
        indice = next((modelos.index(c) for c in candidatos if c and c in modelos), 0)
        self._cargando = True                     # sin _al_elegir por cada addItem
        try:
            self.combo.clear()
            for m in modelos:
                self.combo.addItem(m, m)
            if not modelos:
                self.combo.addItem("No hay modelos en modelo_vrm/", None)
            self.combo.setCurrentIndex(indice)
        finally:
            self._cargando = False
        self.combo.setEnabled(bool(modelos))
        self._al_elegir(indice)

    def _al_elegir(self, _indice: int = 0) -> None:
        if self._cargando:
            return
        self.guardar_ya()
        nombre = self.modelo
        hay = bool(nombre)
        self._meta = vrm.meta(vrm.CARPETA / nombre) if hay else {}
        self._pintar_ficha()
        self._pintar_miniatura()
        activo = str(self._personaje_activo().get("nombre") or "") or "el personaje"
        usa = self._modelo_de_activo()
        self.btn_asignar.setText(f"USAR CON {activo.upper()}")
        self.btn_asignar.setEnabled(hay and usa != nombre)
        self.btn_quitar.setEnabled(bool(str(self._personaje_activo().get("vrm") or "").strip()))
        self._cargando = True
        try:
            for clave, s in self.sliders.items():
                v = self.peso(nombre, clave) if hay else float(vrm.AJUSTES[clave]["defecto"])
                s.setValue(int(round(v * 100)))
                self._valores[clave].setText(f"{s.value()} %")
                s.setEnabled(hay)
        finally:
            self._cargando = False
        sin_ojos = hay and not self._meta.get("tieneLookAt", False)
        self.aviso_ojos.setVisible(sin_ojos)
        self.sliders["pesoOjos"].setEnabled(hay and not sin_ojos)

    def _pintar_ficha(self) -> None:
        m = self._meta
        if not m:
            self.ficha.setText("Copia un .vrm con «Importar» (VRoid Hub, Booth…).")
            return
        partes = [f"VRM {'1.0' if m.get('version') == '1' else '0.x'}"]
        if m.get("nombre"):
            partes.append(str(m["nombre"]))
        if m.get("autor"):
            partes.append(f"de {m['autor']}")
        partes.append(f"{m.get('mb', 0)} MB")
        lineas = [" · ".join(partes)]
        if m.get("licencia"):
            lineas.append(str(m["licencia"]))
        try:
            quien = vrm.personajes_con(self.modelo)
        except Exception:
            quien = []
        if quien:
            lineas.append("Lo usa: " + ", ".join(quien))
        if m.get("motivo"):
            lineas.append(str(m["motivo"]))
        self.ficha.setText("\n".join(lineas))

    def _pintar_miniatura(self) -> None:
        datos = vrm.miniatura(vrm.CARPETA / self.modelo) if self.modelo else None
        pm = QPixmap()
        if datos and pm.loadFromData(datos):
            self.miniatura.setPixmap(pm.scaled(TAM_MINIATURA - 4, TAM_MINIATURA - 4,
                                               Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            self.miniatura.setText("")
        else:
            self.miniatura.setPixmap(QPixmap())
            self.miniatura.setText("3D" if self.modelo else "—")

    # ── Acciones ─────────────────────────────────────────────────────────────────
    def _aviso(self, texto: str, error: bool = False) -> None:
        self.estado.setText(texto)
        self.estado.setStyleSheet(f"color:{COLORS['error'] if error else COLORS['text_muted']};border:none;")

    def importar(self) -> str:
        """Pide un .vrm y lo copia a modelo_vrm/. Devuelve el archivo importado ("" si no)."""
        try:
            ruta = str(self._elegir_archivo() or "").strip()
        except Exception as e:
            self._aviso(f"No pude abrir el selector: {e}", error=True)
            return ""
        if not ruta:
            return ""
        try:
            nombre = vrm.importar_modelo(ruta)
        except (ValueError, OSError) as e:
            self._aviso(f"No pude importar «{Path(ruta).name}»: {e}", error=True)
            return ""
        self.recargar(elegir=nombre)
        self._aviso(f"Importado «{nombre}».")
        self.cambiado.emit()
        return nombre

    def asignar(self) -> bool:
        """El modelo elegido pasa a ser el del personaje activo."""
        return self._asignar(self.modelo)

    def quitar(self) -> bool:
        """El personaje activo deja de tener modelo propio (usa el de config o el primero)."""
        return self._asignar("")

    def _asignar(self, archivo: str) -> bool:
        activo = str(self._personaje_activo().get("nombre") or "")
        if not activo:
            self._aviso("No hay personaje activo.", error=True)
            return False
        try:
            vrm.asignar_a_personaje(activo, archivo)
        except (ValueError, OSError) as e:
            self._aviso(str(e), error=True)
            return False
        self._al_elegir()
        self._aviso(f"{activo} usa ahora «{archivo}»." if archivo else f"{activo} vuelve al modelo por defecto.")
        self.cambiado.emit()
        return True

    # ── Seguimiento ──────────────────────────────────────────────────────────────
    def _al_mover(self, clave: str, valor: int) -> None:
        self._valores[clave].setText(f"{valor} %")
        if self._cargando or not self.modelo:
            return
        if self._pendiente_modelo and self._pendiente_modelo != self.modelo:
            self.guardar_ya()
        self._pendiente_modelo = self.modelo
        self._pendientes[clave] = round(valor / 100.0, 2)
        self._timer.start()

    @property
    def pendiente(self) -> bool:
        """¿Hay cambios de seguimiento sin escribir todavía?"""
        return bool(self._pendientes)

    def guardar_ya(self) -> bool:
        """Escribe ya los pesos pendientes en modelo_vrm/<modelo>.lune.json."""
        self._timer.stop()
        if not self._pendientes or not self._pendiente_modelo:
            self._pendientes.clear()
            return False
        modelo, cambios = self._pendiente_modelo, dict(self._pendientes)
        self._pendientes.clear()
        self._pendiente_modelo = ""
        try:
            vrm.guardar_ajustes_modelo(modelo, cambios)
        except (ValueError, OSError) as e:
            self._aviso(f"No pude guardar el seguimiento: {e}", error=True)
            return False
        self._aviso(f"Seguimiento guardado para «{modelo}».")
        self.cambiado.emit()
        return True

    def hideEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        self.guardar_ya()                                              # no perder el último ajuste
        super().hideEvent(ev)


__all__ = ("VrmPanelNativo", "SEGUIMIENTO")
