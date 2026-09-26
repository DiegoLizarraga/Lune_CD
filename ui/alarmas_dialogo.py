"""
ui/alarmas_dialogo.py — Las dos ventanas Qt de las alarmas.

- `DialogoAlarma`: la tarjeta que sale al sonar cuando no hay pantalla grande
  (alarmas.pantalla_grande desactivado, sprites o sin mascota). Sin bordes,
  siempre encima, abajo a la derecha, sin robar el foco. Texto de la alarma,
  la hora y dos botones: «Apagar» (con la cuenta atrás del bloqueo: «Apagar
  (4)») y «Posponer N min». Señales `apagar` y `posponer`.
- `DialogoAlarmas`: el editor de la interfaz nativa (tile ALARMAS y acción
  «alarma»): alarmas con hora, días L M X J V S D, «Una vez», texto, interruptor
  y papelera; temporizadores h/m/s con cuenta atrás, Iniciar/Parar, Reiniciar y
  Borrar; «Probar» y el interruptor general `alarmas.activo`. Habla con
  ControlAlarmasQt (listar, guardar_alarma, crear_temporizador, borrar,
  temporizador_accion, probar) y se refresca con su señal `cambio`.

Estilo de ui/theme.py (COLORS) como el resto de la nativa; el rojo de la alarma
es el de Mate-Engine (#FF4826).

Todas las etiquetas con textos de alarmas y temporizadores son de texto PLANO
(revisión 4-5-6, SM1): el texto sale de alarmas.json, del chat o del modelo, y
un QLabel en automático interpretaría «<img src=//host/x>» (carga por UNC) o
«<b>/<font>» para suplantar.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QTime, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from nucleo import alarmas as al
from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO

ROJO_ALARMA = "#FF4826"
ANCHO_TARJETA = 380
MARGEN = 24
TITULOS = {"alarma": "ALARMA", "temporizador": "TEMPORIZADOR", "pospuesta": "POSPUESTA",
           "prueba": "PRUEBA"}


def _c(clave: str, defecto: str) -> str:
    return str(COLORS.get(clave, defecto))


def _plano(lbl: QLabel) -> QLabel:
    """El texto tal cual, nunca como HTML."""
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


def _fecha_corta(fecha: str) -> str:
    """«2026-09-27» → «27/09/2026» (tal cual si no es una fecha)."""
    partes = str(fecha or "").split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else str(fecha or "")


# ── Tarjeta al sonar ───────────────────────────────────────────────────────────

class DialogoAlarma(QWidget):
    """La tarjeta roja de la alarma (bajos recursos o sin pantalla grande)."""

    apagar = pyqtSignal()
    posponer = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *, reloj: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self._reloj = reloj
        self._hasta = 0.0                    # reloj en que se podrá apagar
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Lune · alarma")
        self.setFixedWidth(ANCHO_TARJETA)

        caja = QFrame(self)
        caja.setObjectName("tarjetaAlarma")
        caja.setStyleSheet(
            f"#tarjetaAlarma {{ background: {_c('surface', '#0F1424')}; border: 2px solid {ROJO_ALARMA};"
            f" border-radius: 14px; }}"
            f"QLabel {{ color: {_c('text', '#EAF1FF')}; background: transparent; }}"
            f"QPushButton {{ border-radius: 8px; padding: 8px 14px; font-weight: 600; }}"
            f"QPushButton#apagar {{ background: {ROJO_ALARMA}; color: white; border: none; }}"
            f"QPushButton#apagar:disabled {{ background: #7a2a1c; color: #e8c0b8; }}"
            f"QPushButton#posponer {{ background: transparent; color: {_c('text', '#EAF1FF')};"
            f" border: 1px solid {_c('border2', '#415379')}; }}"
            f"QPushButton#posponer:disabled {{ color: {_c('text_dim', '#6E7D9E')}; }}")
        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(0, 0, 0, 0)
        fuera.addWidget(caja)

        lay = QVBoxLayout(caja)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(8)
        cab = QHBoxLayout()
        self.titulo = _plano(QLabel("⏰ ALARMA"))
        self.titulo.setStyleSheet(f"color: {ROJO_ALARMA}; font-family: '{FONT_DISPLAY}'; font-size: 13px;"
                                  " font-weight: 700; letter-spacing: 2px;")
        self.hora = _plano(QLabel(""))
        self.hora.setStyleSheet(f"font-family: '{FONT_MONO}'; font-size: 13px; color: {_c('text_muted', '#97A6C4')};")
        cab.addWidget(self.titulo)
        cab.addStretch(1)
        cab.addWidget(self.hora)
        lay.addLayout(cab)

        self.texto = _plano(QLabel(""))
        self.texto.setWordWrap(True)
        self.texto.setStyleSheet("font-size: 17px; font-weight: 600;")
        lay.addWidget(self.texto)
        self.cola = _plano(QLabel(""))
        self.cola.setStyleSheet(f"font-size: 11px; color: {_c('text_dim', '#6E7D9E')};")
        self.cola.hide()
        lay.addWidget(self.cola)

        botones = QHBoxLayout()
        botones.addStretch(1)
        self.boton_posponer = QPushButton("Posponer 5 min")
        self.boton_posponer.setObjectName("posponer")
        self.boton_apagar = QPushButton("Apagar")
        self.boton_apagar.setObjectName("apagar")
        for b in (self.boton_posponer, self.boton_apagar):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            botones.addWidget(b)
        lay.addLayout(botones)
        self.boton_apagar.clicked.connect(self._pulsar_apagar)
        self.boton_posponer.clicked.connect(self._pulsar_posponer)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._actualizar_bloqueo)

    # ── API ──
    def set_disparo(self, texto: str, *, tipo: str = "alarma", programado: str = "", bloqueo_ms: int = 0,
                    posponer_min: float = 5, cola: int = 0) -> None:
        self.titulo.setText(("⏲ " if tipo in ("temporizador", "pospuesta") else "⏰ ")
                            + TITULOS.get(tipo, "ALARMA"))
        self.hora.setText(str(programado or ""))
        self.texto.setText(str(texto or al.texto_por_defecto(tipo)))
        self.cola.setText(f"+{cola} en espera" if cola else "")
        self.cola.setVisible(bool(cola))
        mins = max(1, int(round(float(posponer_min or 5))))
        self._txt_posponer = f"Posponer {mins} min"
        self.boton_posponer.setVisible(tipo != "prueba")
        self._hasta = self._reloj() + max(0, int(bloqueo_ms)) / 1000.0
        self._actualizar_bloqueo()
        if self.restante_s() > 0:
            self._timer.start()
        self.adjustSize()

    def restante_s(self) -> float:
        return max(0.0, self._hasta - self._reloj())

    def mostrar(self) -> None:
        """Abajo a la derecha de la pantalla principal, sin quitar el foco a nadie."""
        self.adjustSize()
        pantalla = QGuiApplication.primaryScreen()
        if pantalla is not None:
            g = pantalla.availableGeometry()
            self.move(g.right() - self.width() - MARGEN, g.bottom() - self.height() - MARGEN)
        self.show()
        self.raise_()

    def cerrar(self) -> None:
        self._timer.stop()
        self.hide()

    # ── Internos ──
    def _actualizar_bloqueo(self) -> None:
        falta = self.restante_s()
        bloqueado = falta > 0
        self.boton_apagar.setEnabled(not bloqueado)
        self.boton_posponer.setEnabled(not bloqueado)
        self.boton_apagar.setText(f"Apagar ({math.ceil(falta)})" if bloqueado else "Apagar")
        self.boton_posponer.setText(getattr(self, "_txt_posponer", "Posponer 5 min"))
        if not bloqueado:
            self._timer.stop()

    def _pulsar_apagar(self) -> None:
        if self.restante_s() <= 0:
            self.apagar.emit()

    def _pulsar_posponer(self) -> None:
        if self.restante_s() <= 0:
            self.posponer.emit()


# ── Editor de la nativa ────────────────────────────────────────────────────────

_ESTILO_EDITOR = """
QDialog {{ background: {bg}; }}
QLabel {{ color: {text}; background: transparent; }}
QLabel#seccion {{ font-family: '{display}'; font-size: 12px; font-weight: 700; letter-spacing: 2px;
                 color: {accent}; }}
QLabel#error {{ color: {error}; }}
QLabel#cuenta {{ font-family: '{mono}'; color: {accent}; }}
QLineEdit, QTimeEdit, QSpinBox {{ background: {surface2}; color: {text}; border: 1px solid {border};
                                 border-radius: 6px; padding: 4px 6px; }}
QCheckBox {{ color: {text}; }}
QPushButton {{ background: {surface2}; color: {text}; border: 1px solid {border}; border-radius: 6px;
              padding: 5px 10px; }}
QPushButton:hover {{ background: {surface3}; }}
QPushButton:checked {{ background: {accent}; color: {bg}; border-color: {accent}; }}
QPushButton#primario {{ background: {accent}; color: {bg}; border: none; font-weight: 700; }}
QPushButton#peligro {{ color: {error}; }}
QFrame#fila {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
"""


class DialogoAlarmas(QDialog):
    """Editor de alarmas y temporizadores de la interfaz nativa."""

    def __init__(self, ctl: Any, parent: Optional[QWidget] = None, *,
                 reloj: Callable[[], float] = time.time):
        super().__init__(parent)
        self.ctl = ctl
        self._reloj = reloj
        self._editando: Optional[str] = None
        self._estado: Dict[str, Any] = {}
        self.filas_alarma: Dict[str, Dict[str, QWidget]] = {}
        self.filas_temp: Dict[str, Dict[str, QWidget]] = {}
        self.setWindowTitle("Lune · alarmas y temporizadores")
        self.setMinimumWidth(520)
        self.setStyleSheet(_ESTILO_EDITOR.format(
            bg=_c("bg", "#080B16"), text=_c("text", "#EAF1FF"), accent=_c("accent", "#00E5FF"),
            error=_c("error", "#FF3B5C"), surface=_c("surface", "#0F1424"),
            surface2=_c("surface2", "#141B30"), surface3=_c("surface3", "#1B2440"),
            border=_c("border", "#2E3D66"), display=FONT_DISPLAY, mono=FONT_MONO))

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 16)
        raiz.setSpacing(10)

        cab = QHBoxLayout()
        self.activo = QCheckBox("Alarmas activadas")
        self.activo.toggled.connect(self._cambiar_activo)
        self.boton_probar = QPushButton("Probar")
        self.boton_probar.clicked.connect(lambda: self.ctl.probar())
        cab.addWidget(self.activo)
        cab.addStretch(1)
        cab.addWidget(self.boton_probar)
        raiz.addLayout(cab)

        # ── Alarmas ──
        raiz.addWidget(self._titulo("ALARMAS"))
        self.lista_alarmas = QVBoxLayout()
        self.lista_alarmas.setSpacing(6)
        raiz.addLayout(self.lista_alarmas)
        self.vacio_alarmas = QLabel("Sin alarmas.")
        self.vacio_alarmas.setStyleSheet(f"color: {_c('text_dim', '#6E7D9E')};")
        raiz.addWidget(self.vacio_alarmas)

        form = QHBoxLayout()
        self.hora = QTimeEdit(QTime(7, 0))
        self.hora.setDisplayFormat("HH:mm")
        form.addWidget(self.hora)
        self.botones_dia: List[QPushButton] = []
        for letra in al.DIAS:
            b = QPushButton(letra.upper())
            b.setCheckable(True)
            b.setFixedWidth(30)
            b.setToolTip(al.NOMBRES_DIAS[al.DIAS.index(letra)])
            self.botones_dia.append(b)
            form.addWidget(b)
        self.una_vez = QCheckBox("Una vez")
        form.addWidget(self.una_vez)
        raiz.addLayout(form)
        form2 = QHBoxLayout()
        self.texto = QLineEdit()
        self.texto.setMaxLength(al.MAX_TEXTO)
        self.texto.setPlaceholderText("Texto (opcional): gimnasio, pastillas…")
        self.boton_guardar = QPushButton("Añadir alarma")
        self.boton_guardar.setObjectName("primario")
        self.boton_guardar.clicked.connect(self.guardar)
        self.boton_cancelar = QPushButton("Cancelar")
        self.boton_cancelar.clicked.connect(self.cancelar_edicion)
        self.boton_cancelar.hide()
        form2.addWidget(self.texto, 1)
        form2.addWidget(self.boton_cancelar)
        form2.addWidget(self.boton_guardar)
        raiz.addLayout(form2)
        # Editando una alarma de un día concreto («mañana a las 7»): se dice cuál y qué
        # pasa si se le ponen días o se le quita «Una vez» (la fecha se quita).
        self.nota_fecha = _plano(QLabel(""))
        self.nota_fecha.setWordWrap(True)
        self.nota_fecha.setStyleSheet(f"color: {_c('text_muted', '#97A6C4')};")
        self.nota_fecha.hide()
        raiz.addWidget(self.nota_fecha)
        self.error = _plano(QLabel(""))
        self.error.setObjectName("error")
        self.error.hide()
        raiz.addWidget(self.error)

        # ── Temporizadores ──
        raiz.addWidget(self._titulo("TEMPORIZADORES"))
        self.lista_temps = QVBoxLayout()
        self.lista_temps.setSpacing(6)
        raiz.addLayout(self.lista_temps)
        self.vacio_temps = QLabel("Sin temporizadores.")
        self.vacio_temps.setStyleSheet(f"color: {_c('text_dim', '#6E7D9E')};")
        raiz.addWidget(self.vacio_temps)
        form3 = QHBoxLayout()
        self.t_h, self.t_m, self.t_s = QSpinBox(), QSpinBox(), QSpinBox()
        for sb, maximo, sufijo in ((self.t_h, 99, " h"), (self.t_m, 59, " min"), (self.t_s, 59, " s")):
            sb.setRange(0, maximo)
            sb.setSuffix(sufijo)
            form3.addWidget(sb)
        self.t_m.setValue(10)
        self.t_texto = QLineEdit()
        self.t_texto.setMaxLength(al.MAX_TEXTO)
        self.t_texto.setPlaceholderText("Texto (opcional)")
        form3.addWidget(self.t_texto, 1)
        self.boton_temp = QPushButton("Crear")
        self.boton_temp.setObjectName("primario")
        self.boton_temp.clicked.connect(self.crear_temporizador)
        form3.addWidget(self.boton_temp)
        raiz.addLayout(form3)
        raiz.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._actualizar_cuentas)
        self._timer.start()
        senal = getattr(ctl, "cambio", None)
        if senal is not None:
            try:
                senal.connect(self._on_cambio)
            except Exception:
                pass
        self.refrescar()

    @staticmethod
    def _titulo(texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setObjectName("seccion")
        return lbl

    # ── Datos ──
    def _on_cambio(self, _json: str = "") -> None:
        self.refrescar()

    def refrescar(self) -> None:
        try:
            self._estado = dict(self.ctl.listar() or {})
        except Exception:
            self._estado = {}
        self.activo.blockSignals(True)
        self.activo.setChecked(bool(self._estado.get("activo", True)))
        self.activo.blockSignals(False)
        self._pintar_alarmas(self._estado.get("alarmas") or [])
        self._pintar_temps(self._estado.get("temporizadores") or [])

    @staticmethod
    def _vaciar(lay: QVBoxLayout) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _fila(self) -> QFrame:
        f = QFrame()
        f.setObjectName("fila")
        return f

    def _pintar_alarmas(self, alarmas: List[dict]) -> None:
        self._vaciar(self.lista_alarmas)
        self.filas_alarma = {}
        for a in alarmas:
            fila = self._fila()
            lay = QHBoxLayout(fila)
            lay.setContentsMargins(10, 6, 8, 6)
            chk = QCheckBox()
            chk.setChecked(bool(a.get("activa", True)))
            chk.setToolTip("Encendida")
            chk.toggled.connect(lambda on, i=a["id"]: self._activar(i, on))
            etiqueta = _plano(QLabel(f"{a.get('descripcion') or a.get('hora')}"))
            etiqueta.setWordWrap(True)
            ed = QPushButton("Editar")
            ed.clicked.connect(lambda _=False, x=dict(a): self.editar(x))
            bo = QPushButton("✕")
            bo.setObjectName("peligro")
            bo.setFixedWidth(32)
            bo.setToolTip("Borrar")
            bo.clicked.connect(lambda _=False, i=a["id"]: self._borrar(i))
            lay.addWidget(chk)
            lay.addWidget(etiqueta, 1)
            lay.addWidget(ed)
            lay.addWidget(bo)
            self.lista_alarmas.addWidget(fila)
            self.filas_alarma[a["id"]] = {"fila": fila, "activa": chk, "etiqueta": etiqueta,
                                          "editar": ed, "borrar": bo}
        self.vacio_alarmas.setVisible(not alarmas)

    def _pintar_temps(self, temps: List[dict]) -> None:
        self._vaciar(self.lista_temps)
        self.filas_temp = {}
        for t in temps:
            fila = self._fila()
            lay = QHBoxLayout(fila)
            lay.setContentsMargins(10, 6, 8, 6)
            nombre = al.formato_duracion(t.get("duracion_s", 0))
            if t.get("texto"):
                nombre += f" · {t['texto']}"
            if t.get("pospuesta"):
                nombre += " (pospuesta)"
            etiqueta = _plano(QLabel(nombre))
            cuenta = _plano(QLabel(""))
            cuenta.setObjectName("cuenta")
            marcha = QPushButton("Parar" if t.get("corriendo") else "Iniciar")
            marcha.clicked.connect(lambda _=False, i=t["id"], c=bool(t.get("corriendo")):
                                   self._accion(i, "parar" if c else "iniciar"))
            rei = QPushButton("Reiniciar")
            rei.clicked.connect(lambda _=False, i=t["id"]: self._accion(i, "reiniciar"))
            bo = QPushButton("✕")
            bo.setObjectName("peligro")
            bo.setFixedWidth(32)
            bo.clicked.connect(lambda _=False, i=t["id"]: self._borrar(i))
            lay.addWidget(etiqueta, 1)
            lay.addWidget(cuenta)
            lay.addWidget(marcha)
            lay.addWidget(rei)
            lay.addWidget(bo)
            self.lista_temps.addWidget(fila)
            self.filas_temp[t["id"]] = {"fila": fila, "etiqueta": etiqueta, "cuenta": cuenta,
                                        "marcha": marcha, "reiniciar": rei, "borrar": bo, "datos": dict(t)}
        self.vacio_temps.setVisible(not temps)
        self._actualizar_cuentas()

    def _actualizar_cuentas(self) -> None:
        ahora = self._reloj()
        for f in self.filas_temp.values():
            t = f["datos"]
            if t.get("corriendo") and float(t.get("objetivo") or 0) > 0:
                falta = max(0.0, float(t["objetivo"]) - ahora)
            else:
                falta = float(t.get("restante_s") or t.get("duracion_s") or 0)
            f["cuenta"].setText(al.reloj_restante(falta))

    # ── Acciones ──
    def _mostrar_error(self, texto: str) -> None:
        self.error.setText(texto)
        self.error.setVisible(bool(texto))

    def dias_marcados(self) -> str:
        return "".join(al.DIAS[i] for i, b in enumerate(self.botones_dia) if b.isChecked())

    def guardar(self) -> dict:
        t = self.hora.time()
        datos = {"hora": f"{t.hour():02d}:{t.minute():02d}", "dias": self.dias_marcados(),
                 "una_vez": self.una_vez.isChecked(), "texto": self.texto.text()}
        if self._editando:
            datos["id"] = self._editando
        r = self.ctl.guardar_alarma(datos) or {}
        if not r.get("ok"):
            self._mostrar_error(str(r.get("error") or "No se pudo guardar."))
            return r
        self._mostrar_error("")
        self.cancelar_edicion()
        self.refrescar()
        return r

    def editar(self, a: dict) -> None:
        self._editando = str(a.get("id") or "") or None
        self.hora.setTime(QTime(int(a.get("h", 7)), int(a.get("m", 0))))
        letras = str(a.get("dias") or "")
        for i, b in enumerate(self.botones_dia):
            b.setChecked(al.DIAS[i] in letras)
        self.una_vez.setChecked(bool(a.get("una_vez")))
        self.texto.setText(str(a.get("texto") or ""))
        fecha = str(a.get("fecha") or "")
        self.nota_fecha.setText(f"Solo el {_fecha_corta(fecha)}. Si le pones días o le quitas «Una vez», "
                                "deja de ser solo ese día." if fecha else "")
        self.nota_fecha.setVisible(bool(fecha))
        self.boton_guardar.setText("Guardar cambios")
        self.boton_cancelar.show()

    def cancelar_edicion(self) -> None:
        self._editando = None
        self.texto.clear()
        for b in self.botones_dia:
            b.setChecked(False)
        self.una_vez.setChecked(False)
        self.nota_fecha.setText("")
        self.nota_fecha.hide()
        self.boton_guardar.setText("Añadir alarma")
        self.boton_cancelar.hide()

    def _activar(self, id_: str, on: bool) -> None:
        r = self.ctl.guardar_alarma({"id": id_, "activa": bool(on)}) or {}
        if not r.get("ok"):
            self._mostrar_error(str(r.get("error") or "No se pudo cambiar."))

    def _borrar(self, id_: str) -> None:
        if self._editando == id_:
            self.cancelar_edicion()
        self.ctl.borrar(id_)
        self.refrescar()

    def _accion(self, id_: str, accion: str) -> None:
        self.ctl.temporizador_accion(id_, accion)
        self.refrescar()

    def crear_temporizador(self) -> dict:
        datos = {"h": self.t_h.value(), "m": self.t_m.value(), "s": self.t_s.value(),
                 "texto": self.t_texto.text(), "iniciar": True}
        r = self.ctl.crear_temporizador(datos) or {}
        if not r.get("ok"):
            self._mostrar_error(str(r.get("error") or "No se pudo crear."))
            return r
        self._mostrar_error("")
        self.t_texto.clear()
        self.refrescar()
        return r

    def _cambiar_activo(self, on: bool) -> None:
        cfg = getattr(self.ctl, "config", None)
        try:
            if cfg is not None:
                cfg.set("alarmas", "activo", bool(on))
        except Exception:
            pass
        f = getattr(self.ctl, "recargar_config", None)
        if callable(f):
            f()
        self.refrescar()

    def closeEvent(self, ev) -> None:
        self._timer.stop()
        senal = getattr(self.ctl, "cambio", None)
        if senal is not None:
            try:
                senal.disconnect(self._on_cambio)
            except (TypeError, RuntimeError):
                pass
        super().closeEvent(ev)


__all__ = ("DialogoAlarma", "DialogoAlarmas", "ROJO_ALARMA")
