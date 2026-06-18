"""
settings_panel.py — Panel de Configuración General de Lune CD.
Gestiona APIs y personalidad (datos.json) y las features/avatar (config.json).
"""
import json
import importlib

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QScrollArea, QLabel, QPushButton,
    QLineEdit, QTextEdit, QCheckBox, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import datos
from config import Config
from theme import COLORS, FONT_DISPLAY, FONT_MONO
import lune_face


class SettingsPanel(QFrame):
    saved = pyqtSignal()

    def __init__(self, config: Config = None, parent=None):
        super().__init__(parent)
        self.config = config or Config()
        self.setStyleSheet(f"QFrame{{background:transparent;}}")
        self._load_datos_json()
        self._build()

    def _load_datos_json(self):
        """Carga el archivo datos.json para leer la personalidad y Telegram."""
        try:
            with open("datos.json", "r", encoding="utf-8") as f:
                self.datos_data = json.load(f)
        except Exception:
            self.datos_data = {"apis": {}, "modelos": {}, "bot": {"personaje_default": "Lune"}, "personajes": [{}]}

    def _build(self):
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(0,0,0,0)

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

        # ── SECCIÓN 1: INTELIGENCIA ARTIFICIAL ──
        layout.addWidget(self._create_section_title("Red Neuronal (OpenRouter)"))
        frame_ia = self._create_group_frame()
        fl_ia = QVBoxLayout(frame_ia); fl_ia.setSpacing(10)
        key_or = self.datos_data.get("apis", {}).get("openrouter_key", "")
        mod_or = self.datos_data.get("modelos", {}).get("openrouter_model", "openrouter/auto")
        self._add_input(fl_ia, "openrouter_api_key", "API Key de OpenRouter", key_or, True)
        self._add_input(fl_ia, "openrouter_model", "Modelo Automático", mod_or, False)
        layout.addWidget(frame_ia)

        # ── SECCIÓN 2: TELEGRAM ──
        layout.addWidget(self._create_section_title("Integración Telegram"))
        frame_tg = self._create_group_frame()
        fl_tg = QVBoxLayout(frame_tg); fl_tg.setSpacing(10)
        token_tg = self.datos_data.get("apis", {}).get("telegram_token", "")
        self._add_input(fl_tg, "telegram_token", "Token del Bot de Telegram", token_tg, True)
        layout.addWidget(frame_tg)

        # ── SECCIÓN 3: PERSONALIDAD ──
        layout.addWidget(self._create_section_title("Personalidad y Comportamiento"))
        frame_pers = self._create_group_frame()
        fl_pers = QVBoxLayout(frame_pers); fl_pers.setSpacing(15)

        personaje = {}
        if self.datos_data.get("personajes"): personaje = self.datos_data["personajes"][0]

        self._add_input(fl_pers, "bot_nombre", "Nombre del Asistente", personaje.get("nombre", "Lune"), False)
        self._add_textarea(fl_pers, "bot_system", "Instrucciones del Sistema (System Prompt)", personaje.get("systemPrompt", "Eres Lune, una asistente virtual inteligente y amigable..."), 100)
        self._add_textarea(fl_pers, "bot_saludo", "Mensaje de Bienvenida", personaje.get("fraseInicial", "Buenos días. ¿En qué te puedo ayudar hoy?"), 60)
        layout.addWidget(frame_pers)

        # ── SECCIÓN 4: RENDIMIENTO Y FUNCIONES ──
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
        ]
        for clave, etiqueta in feats:
            chk = QCheckBox(etiqueta); chk.setChecked(self.config.feature(clave, True))
            chk.setFont(QFont("Segoe UI", 10))
            chk.setStyleSheet(f"QCheckBox{{color:{COLORS['text']};border:none;spacing:8px;}}QCheckBox::indicator{{width:16px;height:16px;}}")
            fl_feat.addWidget(chk); self.feature_checks[clave] = chk
        layout.addWidget(frame_feat)

        # ── SECCIÓN 5: APARIENCIA / MODELO (avatar pack) ──
        layout.addWidget(self._create_section_title("Modelo visual de Lune (avatar pack)"))
        frame_av = self._create_group_frame()
        fl_av = QVBoxLayout(frame_av); fl_av.setSpacing(8)
        info_av = QLabel("Elige el set de expresiones. Suelta nuevos packs en lune_face/packs/. "
                         "Próximamente: modelos VRM/Live2D animados (ver ROADMAP_MODELOS.md).")
        info_av.setWordWrap(True); info_av.setFont(QFont("Segoe UI", 9)); info_av.setStyleSheet(f"color:{COLORS['text_muted']};border:none;")
        fl_av.addWidget(info_av)
        self.pack_combo = QComboBox()
        self.pack_combo.addItems(lune_face.listar_packs())
        actual = self.config.get("avatar", "pack", "default")
        if actual in lune_face.listar_packs(): self.pack_combo.setCurrentText(actual)
        self.pack_combo.setStyleSheet(f"QComboBox{{background:{COLORS['surface2']};border:1px solid {COLORS['border']};border-radius:3px;padding:8px 12px;color:{COLORS['text']};}}QComboBox QAbstractItemView{{background:{COLORS['surface2']};color:{COLORS['text']};selection-background-color:{COLORS['accent']};}}")
        fl_av.addWidget(self.pack_combo)
        layout.addWidget(frame_av)

        # Botón Guardar
        save_btn = QPushButton("GUARDAR CONFIGURACIÓN")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor); save_btn.setFont(QFont(FONT_DISPLAY,12,QFont.Weight.Bold)); save_btn.setFixedHeight(50)
        save_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['accent']},stop:1 {COLORS['accent2']});color:{COLORS['bg']};border:none;border-radius:3px;margin-top: 10px;letter-spacing:2px;}}QPushButton:hover{{background:{COLORS['accent2']};}}")
        save_btn.clicked.connect(self._save); layout.addWidget(save_btn); layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _create_section_title(self, text):
        lbl = QLabel(text); lbl.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold)); lbl.setStyleSheet(f"color:{COLORS['accent']}; margin-top: 10px; letter-spacing:1px;")
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

    def _save(self):
        # Asegurar estructura base en dict
        if "apis" not in self.datos_data: self.datos_data["apis"] = {}
        if "modelos" not in self.datos_data: self.datos_data["modelos"] = {}
        if "bot" not in self.datos_data: self.datos_data["bot"] = {}
        if "personajes" not in self.datos_data or not self.datos_data["personajes"]:
            self.datos_data["personajes"] = [{}]

        # Asignar valores
        self.datos_data["apis"]["openrouter_key"] = self.fields["openrouter_api_key"].text().strip()
        self.datos_data["modelos"]["openrouter_model"] = self.fields["openrouter_model"].text().strip()
        self.datos_data["apis"]["telegram_token"] = self.fields["telegram_token"].text().strip()

        nombre_bot = self.fields["bot_nombre"].text().strip()
        self.datos_data["bot"]["personaje_default"] = nombre_bot

        self.datos_data["personajes"][0]["nombre"] = nombre_bot
        self.datos_data["personajes"][0]["systemPrompt"] = self.fields["bot_system"].toPlainText().strip()
        self.datos_data["personajes"][0]["fraseInicial"] = self.fields["bot_saludo"].toPlainText().strip()

        # Guardar en archivo
        try:
            with open("datos.json", "w", encoding="utf-8") as f:
                json.dump(self.datos_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando datos.json: {e}")

        # Guardar features y avatar pack en config.json
        if hasattr(self, "feature_checks"):
            for clave, chk in self.feature_checks.items():
                self.config.config.setdefault("features", {})[clave] = chk.isChecked()
        if hasattr(self, "pack_combo"):
            self.config.config.setdefault("avatar", {})["pack"] = self.pack_combo.currentText()
        self.config.save()

        # Aplicar cambios en caliente
        lune_face.set_anim_video(self.config.feature("animaciones_video", True))
        lune_face.set_active_pack(self.config.get("avatar", "pack", "default"))

        # Emitir señal de guardado y recargar módulos en caliente
        importlib.reload(datos)
        self.saved.emit()
