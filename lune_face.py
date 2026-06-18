"""
lune_face.py — Cara animada de Lune, emociones y avatar packs.
Maneja imágenes/videos de expresión y los packs intercambiables
(base para futuros modelos VRM/Live2D — ver ROADMAP_MODELOS.md).
"""
from pathlib import Path

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QPixmap

from theme import COLORS, FONT_MONO, FONT_JP

# Etiqueta de estado que se muestra en el escenario de la mascota (月 EN LÍNEA)
STATE_LABELS = {
    "normal": "EN LÍNEA", "happy": "OK", "reading": "LEYENDO",
    "thinking": "PENSANDO", "typing": "ESCRIBIENDO",
    "sad": "EN PAUSA", "confused": "???", "error": "ERROR",
}

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_OK = True
except ImportError:
    _MULTIMEDIA_OK = False

FACE_DIR = Path(__file__).parent / "lune_face"

FACE_FILES = {
    "normal":    ("lune_normal.png",    "image"),
    "happy":     ("lune_happy.png",     "image"),
    "thinking":  ("pensando.mp4",       "video"),
    "typing":    ("escribiendo.mp4",    "video"),
    "reading":   ("lune_reading.png",   "image"),
    "sad":       ("lune_sad.png",       "image"),
    "confused":  ("lune_confused.png",  "image"),
    "error":     ("lune_error.png",     "image"),
}

FACE_FALLBACK_IMAGE = {
    "thinking": "lune_thinking.png",
    "typing":   "lune_typing.png",
}

# ── Avatar packs (base para "modelos" intercambiables estilo Mate-Engine) ───────
# Un pack es una subcarpeta en lune_face/packs/<nombre> con los mismos archivos.
# "default" usa directamente lune_face/. Ver ROADMAP_MODELOS.md.
PACKS_DIR = FACE_DIR / "packs"
_ACTIVE_PACK = "default"
_ANIM_VIDEO = True   # se ajusta desde config.json (features.animaciones_video)


def set_active_pack(nombre: str):
    global _ACTIVE_PACK
    _ACTIVE_PACK = nombre or "default"


def set_anim_video(activo: bool):
    global _ANIM_VIDEO
    _ANIM_VIDEO = bool(activo)


def listar_packs() -> list:
    packs = ["default"]
    if PACKS_DIR.exists():
        packs += sorted(p.name for p in PACKS_DIR.iterdir() if p.is_dir())
    return packs


def _pack_path(filename: str):
    """Ruta del archivo dentro del pack activo, o None si no existe ahí."""
    if _ACTIVE_PACK and _ACTIVE_PACK != "default":
        candidato = PACKS_DIR / _ACTIVE_PACK / filename
        if candidato.exists():
            return candidato
    return None


EMOTION_KEYWORDS = {
    "happy": ["perfecto", "excelente", "claro", "con gusto", "por supuesto", "genial", "listo", "hecho", "entendido", "buena idea", "me alegra"],
    "sad": ["lo siento", "disculpa", "disculpe", "perdón", "lamentablemente", "desafortunadamente", "imposible", "no puedo", "fallé"],
    "reading": ["según", "investigando", "información", "encontré que", "de acuerdo a", "datos", "fuentes", "basándome en", "buscando"],
    "typing": ["aquí está", "a continuación", "te presento", "redactando", "escribiendo", "el documento", "el texto", "el código", "generando"],
    "confused": ["no entiendo", "no estoy segura", "no estoy seguro", "podrías aclarar", "¿a qué te refieres", "es ambiguo", "no comprendo"],
    "error": ["✕", "error:", "no se pudo", "falló", "timeout", "conexión rechazada", "api key", "sin respuesta", "excepción"],
}


def detect_emotion(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in EMOTION_KEYWORDS["error"]): return "error"
    for emotion in ["sad", "confused", "happy", "reading", "typing"]:
        if any(kw in text_lower for kw in EMOTION_KEYWORDS[emotion]): return emotion
    return "normal"


def get_face_info(state: str) -> tuple:
    entry = FACE_FILES.get(state, FACE_FILES["normal"])
    filename, kind = entry
    # Si las animaciones de video están desactivadas, usa imagen fija
    if kind == "video" and not _ANIM_VIDEO and state in FACE_FALLBACK_IMAGE:
        fb = _pack_path(FACE_FALLBACK_IMAGE[state]) or (FACE_DIR / FACE_FALLBACK_IMAGE[state])
        if fb and Path(fb).exists(): return str(fb), "image"
    # Prioriza el archivo del pack activo si existe
    pack_file = _pack_path(filename)
    if pack_file: return str(pack_file), kind
    path = FACE_DIR / filename
    if path.exists(): return str(path), kind
    if kind == "video" and state in FACE_FALLBACK_IMAGE:
        fallback_path = FACE_DIR / FACE_FALLBACK_IMAGE[state]
        if fallback_path.exists(): return str(fallback_path), "image"
    return None, "image"


class LuneFaceWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(196, 260)
        # Escenario "Shibuya Punk": fondo tinta + marco neón cyan
        self.setStyleSheet(
            f"LuneFaceWidget {{ background:{COLORS['bg']}; "
            f"border:2px solid {COLORS['cyan_dark']}; border-radius:3px; }}"
        )
        self._current_state = "normal"

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # Etiqueta de estado (月 EN LÍNEA) arriba a la izquierda del escenario
        self.state_tag = QLabel("月 EN LÍNEA")
        self.state_tag.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self.state_tag.setStyleSheet(
            f"color:{COLORS['accent']};background:{COLORS['bg']};"
            f"border:1px solid {COLORS['cyan_dark']};padding:2px 6px;"
        )
        self.state_tag.setAlignment(Qt.AlignmentFlag.AlignLeft)
        tag_row = QVBoxLayout(); tag_row.setContentsMargins(6, 6, 6, 0)
        tag_row.addWidget(self.state_tag, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(tag_row)

        self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.image_label.setScaledContents(False)
        self.image_label.setStyleSheet("background: transparent; border: none;"); layout.addWidget(self.image_label)

        if _MULTIMEDIA_OK:
            self.video_widget = QVideoWidget(); self.video_widget.setFixedSize(190, 250)
            self.video_widget.setStyleSheet("background: transparent; border: none;"); self.video_widget.hide()
            layout.addWidget(self.video_widget)
            self._player = QMediaPlayer(); self._audio  = QAudioOutput(); self._audio.setVolume(0)
            self._player.setAudioOutput(self._audio); self._player.setVideoOutput(self.video_widget)
            self._player.mediaStatusChanged.connect(self._on_media_status)
        else: self.video_widget = None; self._player = None

        self._fallback_label = QLabel("月"); self._fallback_label.setFont(QFont("Yu Gothic UI", 56, QFont.Weight.Bold))
        self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self._fallback_label.setStyleSheet("background: transparent; border: none;")
        self._fallback_label.hide(); layout.addWidget(self._fallback_label)

        self._revert_timer = QTimer(self); self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(lambda: self.set_state("normal")); self._load_face("normal")

    def _on_media_status(self, status):
        if self._player and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0); self._player.play()

    def _stop_video(self):
        if self._player: self._player.stop()
        if self.video_widget: self.video_widget.hide()

    def _load_face(self, state: str):
        path, kind = get_face_info(state); self._stop_video()
        if path and kind == "video" and _MULTIMEDIA_OK and self._player:
            self.image_label.hide(); self._fallback_label.hide(); self.video_widget.show()
            self._player.setSource(QUrl.fromLocalFile(path)); self._player.play(); return
        if path and kind == "image":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(190, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.image_label.setPixmap(scaled); self.image_label.show(); self._fallback_label.hide(); return
        fallback_marks = { "normal": "月", "happy": "月", "thinking": "…", "typing": "…", "reading": "夜", "sad": "夜", "confused": "?", "error": "✕" }
        self._fallback_label.setText(fallback_marks.get(state, "月")); self._fallback_label.show(); self.image_label.hide()

    def set_state(self, state: str, auto_revert_ms: int = 0):
        if state == self._current_state: return
        self._current_state = state; self._load_face(state)
        # Tinte de la etiqueta según el estado (error=rojo, normal/feliz=cyan)
        tag_color = COLORS["error"] if state == "error" else COLORS["accent"]
        self.state_tag.setText(f"月 {STATE_LABELS.get(state, 'EN LÍNEA')}")
        self.state_tag.setStyleSheet(
            f"color:{tag_color};background:{COLORS['bg']};"
            f"border:1px solid {tag_color};padding:2px 6px;"
        )
        if auto_revert_ms > 0: self._revert_timer.start(auto_revert_ms)
        else: self._revert_timer.stop()
