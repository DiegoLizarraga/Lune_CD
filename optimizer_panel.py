"""
optimizer_panel.py — Centro de optimización estilo Stacer (UI + worker).
Monitorea CPU/RAM/Disco, libera espacio (temporales, caché, papelera) y
permite cerrar procesos pesados, todo sin congelar la interfaz.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from config import Config
from theme import COLORS, FONT_DISPLAY, FONT_MONO
from optimizador import Optimizador, formatear_bytes
from utils import log_error


class OptimizadorWorker(QThread):
    progreso = pyqtSignal(str)
    escaneo_listo = pyqtSignal(object)     # list[CategoriaLimpieza]
    limpieza_lista = pyqtSignal(object)    # dict resultado
    procesos_listos = pyqtSignal(object)   # list[dict]

    def __init__(self, optimizador, modo="scan", claves=None):
        super().__init__()
        self.opt = optimizador
        self.modo = modo
        self.claves = claves or []

    def run(self):
        try:
            if self.modo == "scan":
                cats = self.opt.escanear(lambda m: self.progreso.emit(m))
                self.escaneo_listo.emit(cats)
            elif self.modo == "clean":
                res = self.opt.limpiar(self.claves, lambda m: self.progreso.emit(m))
                self.limpieza_lista.emit(res)
            elif self.modo == "procs":
                self.procesos_listos.emit(self.opt.procesos_pesados(10))
        except Exception as e:
            log_error(f"OptimizadorWorker: {e}")
            self.progreso.emit(f"Error: {e}")


class OptimizadorPanel(QFrame):
    """Centro de limpieza y monitoreo del PC, estilo Stacer."""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.opt = Optimizador()
        self._worker = None
        self._checks = {}        # clave -> (QCheckBox, CategoriaLimpieza)
        self.setStyleSheet("QFrame{background:transparent;}")
        self._build()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refrescar_stats)
        self._stats_timer.start(3000)
        QTimer.singleShot(200, self._refrescar_stats)

    # ── Construcción ───────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:transparent;}}QScrollBar:vertical{{background:{COLORS['surface']};width:8px;border-radius:4px;}}QScrollBar::handle:vertical{{background:{COLORS['border2']};border-radius:4px;}}")
        content = QFrame(); layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 22, 36, 36); layout.setSpacing(18)

        title = QLabel("OPTIMIZADOR DEL SISTEMA")
        title.setFont(QFont(FONT_DISPLAY, 18, QFont.Weight.Bold)); title.setStyleSheet(f"color:{COLORS['text']};letter-spacing:2px;")
        layout.addWidget(title)
        sub = QLabel("Libera espacio y mantén tu PC ligero. Limpieza segura: solo toco archivos temporales y caché.")
        sub.setWordWrap(True); sub.setFont(QFont(FONT_MONO, 9)); sub.setStyleSheet(f"color:{COLORS['text_muted']};")
        layout.addWidget(sub)

        # ── Monitor en vivo ──
        layout.addWidget(self._titulo_seccion("Monitor en vivo"))
        mon = self._grupo()
        ml = QVBoxLayout(mon); ml.setSpacing(12)
        self.bar_cpu = self._barra("CPU", COLORS["accent"])
        self.bar_ram = self._barra("RAM", COLORS["telegram"])
        self.bar_disco = self._barra("Disco", COLORS["warning"])
        for b in (self.bar_cpu, self.bar_ram, self.bar_disco):
            ml.addLayout(b["row"])
        layout.addWidget(mon)

        # ── Limpieza ──
        layout.addWidget(self._titulo_seccion("Liberar espacio"))
        self.grupo_limpieza = self._grupo()
        self.ll = QVBoxLayout(self.grupo_limpieza); self.ll.setSpacing(8)
        self.lbl_scan = QLabel("Pulsa «Escanear» para ver cuánta basura puedo limpiar.")
        self.lbl_scan.setWordWrap(True); self.lbl_scan.setFont(QFont("Segoe UI", 10)); self.lbl_scan.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self.ll.addWidget(self.lbl_scan)
        layout.addWidget(self.grupo_limpieza)

        botones = QHBoxLayout(); botones.setSpacing(10)
        self.btn_scan = self._boton("Escanear", COLORS["accent"], COLORS["accent2"])
        self.btn_scan.clicked.connect(self._escanear)
        self.btn_clean = self._boton("Limpiar seleccionado", COLORS["success"], COLORS["ollama_dark"])
        self.btn_clean.clicked.connect(self._limpiar); self.btn_clean.setEnabled(False)
        botones.addWidget(self.btn_scan); botones.addWidget(self.btn_clean); botones.addStretch()
        layout.addLayout(botones)

        # ── Procesos ──
        layout.addWidget(self._titulo_seccion("Procesos que más consumen"))
        self.grupo_procs = self._grupo()
        self.pl = QVBoxLayout(self.grupo_procs); self.pl.setSpacing(6)
        self.lbl_procs = QLabel("Pulsa «Ver procesos» para listar los que más RAM usan.")
        self.lbl_procs.setFont(QFont("Segoe UI", 10)); self.lbl_procs.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self.pl.addWidget(self.lbl_procs)
        layout.addWidget(self.grupo_procs)
        self.btn_procs = self._boton("Ver procesos", COLORS["telegram"], COLORS["telegram_dark"])
        self.btn_procs.clicked.connect(self._ver_procesos)
        fila_p = QHBoxLayout(); fila_p.addWidget(self.btn_procs); fila_p.addStretch()
        layout.addLayout(fila_p)

        layout.addStretch()
        scroll.setWidget(content); outer.addWidget(scroll)

    # ── Helpers de UI ──────────────────────────────────────────────────────────
    def _titulo_seccion(self, t):
        lbl = QLabel(t); lbl.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{COLORS['accent']};margin-top:6px;letter-spacing:1px;"); return lbl

    def _grupo(self):
        f = QFrame(); f.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border-radius:3px;border:1px solid {COLORS['border']};padding:14px;}}")
        return f

    def _boton(self, texto, c, d):
        b = QPushButton(texto); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(FONT_DISPLAY, 11, QFont.Weight.Bold)); b.setFixedHeight(44)
        b.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {d},stop:1 {c});color:{COLORS['bg']};border:none;border-radius:3px;padding:0 18px;letter-spacing:1px;}}QPushButton:hover{{background:{c};}}QPushButton:disabled{{background:{COLORS['surface3']};color:{COLORS['text_dim']};}}")
        return b

    def _barra(self, etiqueta, color):
        row = QHBoxLayout(); row.setSpacing(10)
        lbl = QLabel(etiqueta); lbl.setFixedWidth(80); lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']};border:none;")
        bar = QProgressBar(); bar.setTextVisible(True); bar.setFixedHeight(20); bar.setRange(0, 100)
        bar.setStyleSheet(f"QProgressBar{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;color:{COLORS['text']};text-align:center;font-size:10px;}}QProgressBar::chunk{{background:{color};border-radius:2px;}}")
        val = QLabel("—"); val.setFixedWidth(120); val.setFont(QFont("Segoe UI", 9)); val.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        row.addWidget(lbl); row.addWidget(bar, 1); row.addWidget(val)
        return {"row": row, "bar": bar, "val": val}

    # ── Monitor ────────────────────────────────────────────────────────────────
    def _refrescar_stats(self):
        s = self.opt.estadisticas_sistema()
        if not s.get("disponible"):
            self.bar_cpu["val"].setText("psutil no instalado"); return
        self.bar_cpu["bar"].setValue(int(s["cpu"])); self.bar_cpu["val"].setText(f"{s['cpu']:.0f}%")
        self.bar_ram["bar"].setValue(int(s["ram_pct"])); self.bar_ram["val"].setText(f"{s['ram_usada']} / {s['ram_total']}")
        self.bar_disco["bar"].setValue(int(s["disco_pct"])); self.bar_disco["val"].setText(f"{s['disco_libre']} libres")

    # ── Escaneo ────────────────────────────────────────────────────────────────
    def _escanear(self):
        self.btn_scan.setEnabled(False); self.btn_scan.setText("Escaneando…")
        self.lbl_scan.setText("Buscando archivos temporales y caché… esto puede tardar unos segundos.")
        self._worker = OptimizadorWorker(self.opt, "scan")
        self._worker.progreso.connect(lambda m: self.lbl_scan.setText(m))
        self._worker.escaneo_listo.connect(self._mostrar_escaneo)
        self._worker.start()

    def _mostrar_escaneo(self, cats):
        self.btn_scan.setEnabled(True); self.btn_scan.setText("Escanear de nuevo")
        # Limpiar contenido previo
        while self.ll.count():
            item = self.ll.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._checks.clear()
        activas = set(self.config.get("optimizador", "categorias_activas",
                                      ["temp_usuario", "temp_windows", "miniaturas", "cache_navegadores"]))
        total = sum(c.tamano for c in cats)
        encabezado = QLabel(f"Encontré <b>{formatear_bytes(total)}</b> limpiables. Marca lo que quieras borrar:")
        encabezado.setFont(QFont("Segoe UI", 10)); encabezado.setStyleSheet(f"color:{COLORS['text']};border:none;")
        self.ll.addWidget(encabezado)
        for c in cats:
            chk = QCheckBox(f"{c.icono}  {c.nombre} — {formatear_bytes(c.tamano)}  ({c.archivos} archivos)")
            chk.setChecked(c.clave in activas)
            chk.setFont(QFont("Segoe UI", 10))
            chk.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
            chk.setToolTip(c.descripcion)
            self.ll.addWidget(chk)
            self._checks[c.clave] = (chk, c)
        self.btn_clean.setEnabled(True)

    # ── Limpieza ───────────────────────────────────────────────────────────────
    def _limpiar(self):
        claves = [k for k, (chk, _c) in self._checks.items() if chk.isChecked()]
        if not claves:
            QMessageBox.information(self, "Nada seleccionado", "Marca al menos una categoría para limpiar "); return
        if self.config.get("optimizador", "confirmar_antes_de_limpiar", True):
            r = QMessageBox.question(self, "Confirmar limpieza",
                                     "¿Borro los archivos temporales seleccionados?\n(Es seguro: no toco tus documentos.)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes: return
        # Recordar selección
        self.config.set("optimizador", "categorias_activas", claves)
        self.btn_clean.setEnabled(False); self.btn_clean.setText("Limpiando…")
        self._worker = OptimizadorWorker(self.opt, "clean", claves)
        self._worker.progreso.connect(lambda m: self.lbl_scan.setText(m))
        self._worker.limpieza_lista.connect(self._mostrar_limpieza)
        self._worker.start()

    def _mostrar_limpieza(self, res):
        self.btn_clean.setText("Limpiar seleccionado"); self.btn_clean.setEnabled(True)
        detalle = "\n".join(res.get("detalle", []))
        msg = (f"¡Listo! Liberé aproximadamente <b>{formatear_bytes(res['liberado'])}</b> "
               f"({res['archivos']} archivos).\n\n{detalle}")
        if res.get("errores"):
            msg += f"\n\n({res['errores']} archivos estaban en uso y los dejé intactos.)"
        QMessageBox.information(self, "Optimización completa", msg)
        self.lbl_scan.setText("¡Tu PC está más ligero! Vuelve a escanear cuando quieras.")

    # ── Procesos ───────────────────────────────────────────────────────────────
    def _ver_procesos(self):
        self.btn_procs.setEnabled(False); self.btn_procs.setText("Cargando…")
        self._worker = OptimizadorWorker(self.opt, "procs")
        self._worker.procesos_listos.connect(self._mostrar_procesos)
        self._worker.start()

    def _mostrar_procesos(self, procs):
        self.btn_procs.setEnabled(True); self.btn_procs.setText("Actualizar procesos")
        while self.pl.count():
            item = self.pl.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not procs:
            lbl = QLabel("No pude leer los procesos (¿psutil instalado?)."); lbl.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
            self.pl.addWidget(lbl); return
        for p in procs:
            nombre = QLabel(f"{p['nombre']}"); nombre.setFont(QFont("Segoe UI", 10)); nombre.setStyleSheet(f"color:{COLORS['text']};border:none;")
            ram = QLabel(p["ram_str"]); ram.setFixedWidth(90); ram.setFont(QFont("Segoe UI", 9)); ram.setStyleSheet(f"color:{COLORS['warning']};border:none;")
            cerrar = QPushButton("Cerrar"); cerrar.setCursor(Qt.CursorShape.PointingHandCursor); cerrar.setFixedHeight(28)
            cerrar.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['error']};border:1px solid {COLORS['error']}55;border-radius:2px;padding:0 10px;font-size:11px;}}QPushButton:hover{{background:{COLORS['error']}33;}}")
            cerrar.clicked.connect(lambda _=False, pid=p["pid"], nom=p["nombre"]: self._cerrar_proceso(pid, nom))
            w = QFrame(); wl = QHBoxLayout(w); wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(nombre, 1); wl.addWidget(ram); wl.addWidget(cerrar)
            w.setStyleSheet("QFrame{border:none;}")
            self.pl.addWidget(w)

    def _cerrar_proceso(self, pid, nombre):
        r = QMessageBox.question(self, "Cerrar proceso",
                                 f"¿Cerrar «{nombre}» (PID {pid})?\nGuarda tu trabajo antes.",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes: return
        ok, msg = self.opt.matar_proceso(pid)
        QMessageBox.information(self, "Resultado", ("" if ok else "") + msg)
        if ok: self._ver_procesos()

    def closeEvent(self, event):
        self._stats_timer.stop(); event.accept()
