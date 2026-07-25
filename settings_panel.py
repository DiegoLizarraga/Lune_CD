"""
settings_panel.py — Panel de Configuración General de Lune CD.
Gestiona APIs, modelos (nube y local) y personalidad (datos.json), además de
las features y el avatar pack (config.json).
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton,
    QLineEdit, QTextEdit, QCheckBox, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

import datos
import ollama_client
from config import Config
from theme import COLORS, FONT_DISPLAY, FONT_MONO
import lune_face


class SondeoOllamaWorker(QThread):
    """Consulta /api/tags en segundo plano para no congelar la UI."""
    listo = pyqtSignal(bool, object, str)   # ok, modelos, mensaje

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        ok, modelos, mensaje = ollama_client.listar_modelos(self.url)
        self.listo.emit(ok, modelos, mensaje)


class SettingsPanel(QFrame):
    saved = pyqtSignal()

    def __init__(self, config: Config = None, parent=None):
        super().__init__(parent)
        self.config = config or Config()
        self.setStyleSheet("QFrame{background:transparent;}")
        self._sondeo = None
        self.datos_data = datos.cargar() or {
            "apis": {}, "modelos": {}, "bot": {"personaje_default": "Lune"}, "personajes": []
        }
        self._build()

    # ── Personaje activo ───────────────────────────────────────────────────────
    def _indice_personaje_activo(self) -> int:
        """
        Índice del personaje activo dentro de datos.json.

        Antes se asumía siempre el 0, así que guardar la configuración con un
        personaje importado activo sobrescribía a Lune. Ahora se resuelve por
        nombre y solo se cae al 0 si no hay coincidencia.
        """
        personajes = self.datos_data.get("personajes") or []
        if not personajes:
            self.datos_data["personajes"] = [{}]
            return 0
        activo = (self.datos_data.get("bot", {}).get("personaje_default") or "").lower()
        for i, p in enumerate(personajes):
            if (p.get("nombre") or "").lower() == activo:
                return i
        return 0

    def _build(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }} QScrollBar:vertical {{ background: {COLORS['surface']}; width: 8px; border-radius: 4px; }} QScrollBar::handle:vertical {{ background: {COLORS['border2']}; border-radius: 4px; }}")

        content = QFrame()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 20, 40, 40); layout.setSpacing(25)

        title = QLabel("CONFIGURACIÓN GENERAL")
        title.setFont(QFont(FONT_DISPLAY, 18, QFont.Weight.Bold)); title.setStyleSheet(f"color:{COLORS['text']};letter-spacing:2px;")
        layout.addWidget(title)

        self.fields = {}
        modelos = self.datos_data.get("modelos", {})
        apis = self.datos_data.get("apis", {})

        # ── SECCIÓN 1: NUBE (OpenRouter) ──
        layout.addWidget(self._create_section_title("Red Neuronal · Nube (OpenRouter)"))
        frame_ia = self._create_group_frame()
        fl_ia = QVBoxLayout(frame_ia); fl_ia.setSpacing(10)
        self._add_input(fl_ia, "openrouter_api_key", "API Key de OpenRouter",
                        apis.get("openrouter_key", ""), True)
        self._add_input(fl_ia, "openrouter_model", "Modelo (openrouter/auto enruta solo)",
                        modelos.get("openrouter_model", "openrouter/auto"), False)
        layout.addWidget(frame_ia)

        # ── SECCIÓN 2: LOCAL (Ollama) ──
        layout.addWidget(self._create_section_title("Red Neuronal · Local (Ollama)"))
        layout.addWidget(self._build_ollama_group(modelos))

        # ── SECCIÓN 3: TELEGRAM ──
        layout.addWidget(self._create_section_title("Integración Telegram"))
        frame_tg = self._create_group_frame()
        fl_tg = QVBoxLayout(frame_tg); fl_tg.setSpacing(10)
        self._add_input(fl_tg, "telegram_token", "Token del Bot de Telegram",
                        apis.get("telegram_token", ""), True)
        self._add_input(fl_tg, "telegram_admin_id", "Tu ID de Telegram (comparte memoria con la app)",
                        str(apis.get("telegram_admin_id", "")), False)
        layout.addWidget(frame_tg)

        # ── SECCIÓN 4: PERSONALIDAD ──
        layout.addWidget(self._create_section_title("Personalidad y Comportamiento"))
        frame_pers = self._create_group_frame()
        fl_pers = QVBoxLayout(frame_pers); fl_pers.setSpacing(15)

        idx = self._indice_personaje_activo()
        personaje = self.datos_data["personajes"][idx]
        aviso = QLabel(f"Editando el personaje activo: «{personaje.get('nombre', 'Lune')}». "
                       "Los demás no se tocan.")
        aviso.setWordWrap(True); aviso.setFont(QFont("Segoe UI", 9))
        aviso.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_pers.addWidget(aviso)

        self._add_input(fl_pers, "bot_nombre", "Nombre del Asistente", personaje.get("nombre", "Lune"), False)
        self._add_textarea(fl_pers, "bot_system", "Instrucciones del Sistema (System Prompt)",
                           personaje.get("systemPrompt", "Eres Lune, una asistente virtual inteligente y amigable..."), 100)
        self._add_textarea(fl_pers, "bot_saludo", "Mensaje de Bienvenida",
                           personaje.get("fraseInicial", "Buenos días. ¿En qué te puedo ayudar hoy?"), 60)
        self._add_input(fl_pers, "max_historial", "Turnos de conversación que recuerda (menos = menos contexto)",
                        str(self.datos_data.get("bot", {}).get("max_historial", 20)), False)
        layout.addWidget(frame_pers)

        # ── SECCIÓN 5: RENDIMIENTO Y FUNCIONES ──
        layout.addWidget(self._create_section_title("Rendimiento y Funciones (activa/desactiva para optimizar)"))
        frame_feat = self._create_group_frame()
        fl_feat = QVBoxLayout(frame_feat); fl_feat.setSpacing(8)
        self.feature_checks = {}
        feats = [
            ("respuestas_predeterminadas", "Respuestas instantáneas (sin gastar IA en saludos comunes)"),
            ("streaming_tokens", "Mostrar respuesta letra por letra (streaming)"),
            ("animaciones_video", "Animaciones de video de Lune (consume más CPU/GPU)"),
            ("fondo_estrellas", "Fondo animado en la pantalla de inicio"),
            ("efectos_hover", "Microanimaciones y efectos visuales"),
            ("voz_auto", "Leer cada respuesta en voz alta al iniciar"),
            ("minimizar_a_bandeja", "Al cerrar, mantener Lune en la bandeja del sistema"),
            ("acciones_ia", "Permitir que la IA abra webs y lance apps por su cuenta"),
        ]
        for clave, etiqueta in feats:
            chk = QCheckBox(etiqueta); chk.setChecked(self.config.feature(clave, True))
            chk.setFont(QFont("Segoe UI", 10))
            chk.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
            fl_feat.addWidget(chk); self.feature_checks[clave] = chk
        layout.addWidget(frame_feat)

        # ── SECCIÓN 6: APARIENCIA / MODELO (avatar pack) ──
        layout.addWidget(self._create_section_title("Modelo visual de Lune (avatar pack)"))
        frame_av = self._create_group_frame()
        fl_av = QVBoxLayout(frame_av); fl_av.setSpacing(8)
        info_av = QLabel("Elige el set de expresiones. Suelta nuevos packs en lune_face/packs/. "
                         "Próximamente: modelos VRM/Live2D animados (ver ROADMAP_MODELOS.md).")
        info_av.setWordWrap(True); info_av.setFont(QFont("Segoe UI", 9)); info_av.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_av.addWidget(info_av)
        self.pack_combo = QComboBox()
        packs = lune_face.listar_packs()
        self.pack_combo.addItems(packs)
        actual = self.config.get("avatar", "pack", "default")
        if actual in packs:
            self.pack_combo.setCurrentText(actual)
        self.pack_combo.setStyleSheet(self._estilo_combo())
        fl_av.addWidget(self.pack_combo)
        layout.addWidget(frame_av)

        # Botón Guardar
        save_btn = QPushButton("GUARDAR CONFIGURACIÓN")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor); save_btn.setFont(QFont(FONT_DISPLAY, 12, QFont.Weight.Bold)); save_btn.setFixedHeight(50)
        save_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['accent']},stop:1 {COLORS['accent2']});color:{COLORS['bg']};border:none;border-radius:3px;margin-top: 10px;letter-spacing:2px;}}QPushButton:hover{{background:{COLORS['accent2']};}}")
        save_btn.clicked.connect(self._save); layout.addWidget(save_btn); layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    # ── Grupo de Ollama ────────────────────────────────────────────────────────
    def _build_ollama_group(self, modelos: dict) -> QFrame:
        frame = self._create_group_frame()
        fl = QVBoxLayout(frame); fl.setSpacing(10)

        info = QLabel(
            "Modelos que corren en tu propia máquina: sin costo, sin conexión y sin límites de tokens. "
            "Puedes apuntar a otro PC de la red (por ejemplo el equipo potente) poniendo su IP: "
            "http://192.168.1.50:11434 — en ese equipo Ollama debe arrancar con OLLAMA_HOST=0.0.0.0:11434."
        )
        info.setWordWrap(True); info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl.addWidget(info)

        # URL + botón de sondeo
        self._add_input(fl, "ollama_url", "Servidor de Ollama",
                        modelos.get("ollama_url", "http://localhost:11434"), False)

        fila = QHBoxLayout(); fila.setSpacing(8)
        self.btn_probar = QPushButton("BUSCAR MODELOS")
        self.btn_probar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probar.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); self.btn_probar.setFixedHeight(36)
        self.btn_probar.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:3px;padding:0 16px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}QPushButton:disabled{{color:{COLORS['text_dim']};border-color:{COLORS['border']};}}")
        self.btn_probar.clicked.connect(self._probar_ollama)
        self.lbl_ollama = QLabel("Pulsa «Buscar modelos» para ver qué hay instalado.")
        self.lbl_ollama.setWordWrap(True); self.lbl_ollama.setFont(QFont(FONT_MONO, 9))
        self.lbl_ollama.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fila.addWidget(self.btn_probar); fila.addWidget(self.lbl_ollama, 1)
        fl.addLayout(fila)

        # Modelo: combo editable (se rellena al sondear, pero puedes escribirlo)
        lbl_modelo = QLabel("Modelo local")
        lbl_modelo.setFont(QFont("Segoe UI", 10)); lbl_modelo.setStyleSheet(f"color:{COLORS['text']};border:none;padding:0;")
        self.ollama_combo = QComboBox(); self.ollama_combo.setEditable(True)
        actual = modelos.get("ollama_model", "")
        if actual:
            self.ollama_combo.addItem(actual)
            self.ollama_combo.setCurrentText(actual)
        self.ollama_combo.setStyleSheet(self._estilo_combo())
        fl.addWidget(lbl_modelo); fl.addWidget(self.ollama_combo)

        # Parámetros de inferencia
        avanzado = QLabel("Ajustes de inferencia")
        avanzado.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        avanzado.setStyleSheet(f"color:{COLORS['accent']};border:none;padding-top:6px;")
        fl.addWidget(avanzado)

        self._add_input(fl, "ollama_keep_alive",
                        "Mantener el modelo en VRAM (30m, 1h, -1 = para siempre)",
                        str(modelos.get("ollama_keep_alive", "30m")), False)
        self._add_input(fl, "ollama_num_ctx",
                        "Ventana de contexto en tokens (más = más RAM/VRAM)",
                        str(modelos.get("ollama_num_ctx", 8192)), False)
        self._add_input(fl, "ollama_timeout",
                        "Timeout en segundos (subir si el modelo tarda en cargar en frío)",
                        str(modelos.get("ollama_timeout", 300)), False)
        self._add_input(fl, "temperatura",
                        "Temperatura (0 = preciso, 1 = creativo)",
                        str(modelos.get("temperatura", 0.7)), False)
        return frame

    def _probar_ollama(self):
        url = self.fields["ollama_url"].text().strip()
        self.btn_probar.setEnabled(False); self.btn_probar.setText("BUSCANDO…")
        self.lbl_ollama.setText(f"Conectando con {ollama_client.normalizar_url(url)}…")
        self.lbl_ollama.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        self._sondeo = SondeoOllamaWorker(url)
        self._sondeo.listo.connect(self._on_sondeo)
        self._sondeo.start()

    def _on_sondeo(self, ok, modelos, mensaje):
        self.btn_probar.setEnabled(True); self.btn_probar.setText("BUSCAR MODELOS")
        color = COLORS["success"] if ok else COLORS["error"]
        self.lbl_ollama.setText(mensaje)
        self.lbl_ollama.setStyleSheet(f"color:{color};border:none;")
        if not modelos:
            return
        # Conservamos lo que ya estaba escrito si sigue existiendo
        actual = self.ollama_combo.currentText().strip()
        self.ollama_combo.clear()
        self.ollama_combo.addItems(modelos)
        if actual in modelos:
            self.ollama_combo.setCurrentText(actual)

    # ── Helpers de UI ──────────────────────────────────────────────────────────
    def _estilo_combo(self):
        return (f"QComboBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};"
                f"border-radius:3px;padding:8px 12px;color:{COLORS['text']};}}"
                f"QComboBox QAbstractItemView{{background:{COLORS['surface2']};color:{COLORS['text']};"
                f"selection-background-color:{COLORS['accent']};}}")

    def _create_section_title(self, text):
        lbl = QLabel(text); lbl.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{COLORS['accent']}; margin-top: 10px; letter-spacing:1px;")
        return lbl

    def _create_group_frame(self):
        f = QFrame()
        f.setStyleSheet(f"QFrame {{ background: {COLORS['surface']}; border-radius: 3px; border: 1px solid {COLORS['border']}; padding: 15px; }}")
        return f

    def _add_input(self, layout, key, label_text, default_val, is_password):
        lbl = QLabel(label_text); lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']}; border: none; padding: 0;")
        inp = QLineEdit(); inp.setText(default_val)
        inp.setEchoMode(QLineEdit.EchoMode.Password if is_password else QLineEdit.EchoMode.Normal)
        inp.setStyleSheet(f"QLineEdit{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;padding:10px 12px;color:{COLORS['text']};}}QLineEdit:focus{{border:1px solid {COLORS['accent']};}}")
        self.fields[key] = inp
        layout.addWidget(lbl); layout.addWidget(inp)

    def _add_textarea(self, layout, key, label_text, default_val, height):
        lbl = QLabel(label_text); lbl.setFont(QFont("Segoe UI", 10)); lbl.setStyleSheet(f"color:{COLORS['text']}; border: none; padding: 0;")
        txt = QTextEdit(); txt.setPlainText(default_val); txt.setFixedHeight(height)
        txt.setStyleSheet(f"QTextEdit{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;padding:10px;color:{COLORS['text']};font-family:'Segoe UI';}}QTextEdit:focus{{border:1px solid {COLORS['accent']};}}")
        self.fields[key] = txt
        layout.addWidget(lbl); layout.addWidget(txt)

    @staticmethod
    def _entero(texto, defecto):
        try:
            return int(float(str(texto).strip()))
        except (TypeError, ValueError):
            return defecto

    @staticmethod
    def _flotante(texto, defecto):
        try:
            return float(str(texto).strip().replace(",", "."))
        except (TypeError, ValueError):
            return defecto

    # ── Guardado ───────────────────────────────────────────────────────────────
    def _save(self):
        d = self.datos_data
        d.setdefault("apis", {}); d.setdefault("modelos", {}); d.setdefault("bot", {})
        if not d.get("personajes"):
            d["personajes"] = [{}]

        # APIs
        d["apis"]["openrouter_key"] = self.fields["openrouter_api_key"].text().strip()
        d["apis"]["telegram_token"] = self.fields["telegram_token"].text().strip()
        d["apis"]["telegram_admin_id"] = self.fields["telegram_admin_id"].text().strip()

        # Modelos: nube y local
        d["modelos"]["openrouter_model"] = self.fields["openrouter_model"].text().strip() or "openrouter/auto"
        d["modelos"]["ollama_url"] = ollama_client.normalizar_url(self.fields["ollama_url"].text())
        d["modelos"]["ollama_model"] = self.ollama_combo.currentText().strip()
        d["modelos"]["ollama_keep_alive"] = self.fields["ollama_keep_alive"].text().strip() or "30m"
        d["modelos"]["ollama_num_ctx"] = self._entero(self.fields["ollama_num_ctx"].text(), 8192)
        d["modelos"]["ollama_timeout"] = self._entero(self.fields["ollama_timeout"].text(), 300)
        d["modelos"]["temperatura"] = self._flotante(self.fields["temperatura"].text(), 0.7)

        # Personalidad: SOLO el personaje activo
        idx = self._indice_personaje_activo()
        nombre_bot = self.fields["bot_nombre"].text().strip() or "Lune"
        d["personajes"][idx]["nombre"] = nombre_bot
        d["personajes"][idx]["systemPrompt"] = self.fields["bot_system"].toPlainText().strip()
        d["personajes"][idx]["fraseInicial"] = self.fields["bot_saludo"].toPlainText().strip()
        d["bot"]["personaje_default"] = nombre_bot
        d["bot"]["max_historial"] = self._entero(self.fields["max_historial"].text(), 20)

        datos.guardar(d)

        # Features y avatar pack en config.json
        for clave, chk in self.feature_checks.items():
            self.config.config.setdefault("features", {})[clave] = chk.isChecked()
        self.config.config.setdefault("avatar", {})["pack"] = self.pack_combo.currentText()
        self.config.save()

        # Aplicar cambios en caliente
        lune_face.set_anim_video(self.config.feature("animaciones_video", True))
        lune_face.set_active_pack(self.config.get("avatar", "pack", "default"))

        self.saved.emit()
