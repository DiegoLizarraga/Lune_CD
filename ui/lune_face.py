"""
lune_face.py — Cara animada de Lune, emociones y avatar packs.
Maneja imágenes/videos de expresión y los packs intercambiables
(base para modelos VRM/Live2D; ver avatar_overlay.py).

La mascota de sprites (avatar_overlay.py) pinta el sprite girado/respirando con
`set_pixmap_compuesto(pm)` sin cambiar de estado, y duerme con el estado
`sleeping` (lune_sleeping.png si el pack lo trae; si no, la cara más cercana).
Sentada (corte 7) usa `sitting` (lune_sitting.png) como cara de reposo SOLO si el pack
la trae (`tiene_cara`): `set_reposo('sitting')` hace que las vueltas a normal caigan
ahí; sin archivo, la de siempre.
"""
from pathlib import Path

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap

from ui.theme import COLORS, FONT_MONO, FONT_JP

# Etiqueta de estado que se muestra en el escenario de la mascota (月 EN LÍNEA)
STATE_LABELS = {
    "normal": "EN LÍNEA", "happy": "OK", "reading": "LEYENDO",
    "thinking": "PENSANDO", "typing": "ESCRIBIENDO",
    "sad": "EN PAUSA", "confused": "???", "error": "ERROR",
    "sleeping": "DURMIENDO", "sitting": "SENTADA",
}

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_OK = True
except ImportError:
    _MULTIMEDIA_OK = False

FACE_DIR = Path(__file__).parent.parent / "lune_face"

FACE_FILES = {
    "normal":    ("lune_normal.png",    "image"),
    "happy":     ("lune_happy.png",     "image"),
    "thinking":  ("pensando.mp4",       "video"),
    "typing":    ("escribiendo.mp4",    "video"),
    "reading":   ("lune_reading.png",   "image"),
    "sad":       ("lune_sad.png",       "image"),
    "confused":  ("lune_confused.png",  "image"),
    "error":     ("lune_error.png",     "image"),
    "sleeping":  ("lune_sleeping.png",  "image"),
    "sitting":   ("lune_sitting.png",   "image"),     # opcional (corte 7): sentada en un borde
}

FACE_FALLBACK_IMAGE = {
    "thinking": "lune_thinking.png",
    "typing":   "lune_typing.png",
}

# Estado sin archivo propio (ni en el pack ni en lune_face/) → la cara más cercana.
# Dormida: «EN PAUSA» (sad) es la de ojos bajos; la mascota además la oscurece.
FACE_FALLBACK_STATE = {
    "sleeping": "sad",
    "sitting": "normal",
}

# ── Avatar packs (base para "modelos" intercambiables estilo Mate-Engine) ───────
# Un pack es una subcarpeta en lune_face/packs/<nombre> con los mismos archivos.
# "default" usa directamente lune_face/.
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


# Emoción canónica del protocolo <|ACT|> (lune_core) → estado visual de la cara.
EMOCION_A_ESTADO = {
    "happy": "happy", "sad": "sad", "angry": "error", "think": "thinking",
    "surprised": "happy", "awkward": "confused", "question": "confused",
    "curious": "reading", "neutral": "normal",
    # v10 / v10.1 (los sprites no tienen cara propia: se aproximan)
    "nervous": "confused", "wave": "happy", "dismiss": "normal",
    "laughing": "happy", "bored": "sad",
}


def estado_desde_emocion(emocion: str) -> str:
    return EMOCION_A_ESTADO.get((emocion or "").lower(), "normal")


def detect_emotion(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in EMOTION_KEYWORDS["error"]): return "error"
    for emotion in ["sad", "confused", "happy", "reading", "typing"]:
        if any(kw in text_lower for kw in EMOTION_KEYWORDS[emotion]): return emotion
    return "normal"


def tiene_cara(state: str) -> bool:
    """¿El estado tiene archivo PROPIO (en el pack activo o en lune_face/), sin caer
    en la cara más cercana? (p. ej. `sitting` solo si existe lune_sitting.png)."""
    entry = FACE_FILES.get(state)
    if entry is None:
        return False
    filename = entry[0]
    return _pack_path(filename) is not None or (FACE_DIR / filename).exists()


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
    if state in FACE_FALLBACK_STATE:
        return get_face_info(FACE_FALLBACK_STATE[state])
    return None, "image"


class LuneFaceWidget(QFrame):
    # Avisa a quien la contiene (p.ej. el overlay) de que cambió la cara, para
    # que pueda recalcular la máscara de silueta (click-through).
    estado_cambiado = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_actual = None      # pixmap escalado que se está mostrando (o None)
        self.setFixedSize(196, 260)
        # Escenario "Shibuya Punk": fondo tinta + marco neón cyan
        self.setStyleSheet(
            f"LuneFaceWidget {{ background:{COLORS['bg']}; "
            f"border:2px solid {COLORS['cyan_dark']}; border-radius:3px; }}"
        )
        self._current_state = "normal"
        self._reposo = "normal"          # a dónde vuelve sola la cara (sentada: `sitting`)

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # Etiqueta de estado (月 EN LÍNEA) arriba a la izquierda del escenario
        self.state_tag = QLabel("月 EN LÍNEA")
        self.state_tag.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self.state_tag.setStyleSheet(
            f"color:{COLORS['accent']};background:{COLORS['bg']};"
            f"border:1px solid {COLORS['cyan_dark']};padding:2px 6px;"
        )
        self.state_tag.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._tag_flotante = False
        self._tag_row = QVBoxLayout(); self._tag_row.setContentsMargins(6, 6, 6, 0)
        self._tag_row.addWidget(self.state_tag, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(self._tag_row)

        self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.image_label.setScaledContents(False)
        self.image_label.setStyleSheet("background: transparent; border: none;"); layout.addWidget(self.image_label)

        if _MULTIMEDIA_OK:
            # Reproductor hijo de la cara y creado ANTES que su vídeo: Qt borra los hijos
            # en orden, así se va antes que la superficie donde pinta (sin padre, lo
            # soltaba el recolector de Python cuando quisiera, con el vídeo ya borrado).
            self._player = QMediaPlayer(self); self._audio = QAudioOutput(self); self._audio.setVolume(0)
            self.video_widget = QVideoWidget(); self.video_widget.setFixedSize(190, 250)
            self.video_widget.setStyleSheet("background: transparent; border: none;"); self.video_widget.hide()
            # Centrado como el sprite (image_label lo centra): pasar a «pensando» no salta.
            layout.addWidget(self.video_widget, 0, Qt.AlignmentFlag.AlignCenter)
            self._player.setAudioOutput(self._audio); self._player.setVideoOutput(self.video_widget)
            self._player.mediaStatusChanged.connect(self._on_media_status)
        else: self.video_widget = None; self._player = None

        self._fallback_label = QLabel("月"); self._fallback_label.setFont(QFont("Yu Gothic UI", 56, QFont.Weight.Bold))
        self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self._fallback_label.setStyleSheet("background: transparent; border: none;")
        self._fallback_label.hide(); layout.addWidget(self._fallback_label)

        # Vuelta a normal: un método (no una lambda), así la conexión muere con la cara.
        self._revert_timer = QTimer(self); self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(self._volver_a_normal); self._load_face("normal")

    def _volver_a_normal(self):
        self.set_state(self._reposo)

    def set_reposo(self, state: str):
        """La cara de reposo (a la que vuelven las caras con tiempo): `normal` o, sentada
        y si el pack la trae, `sitting`."""
        self._reposo = str(state or "normal")

    def _on_media_status(self, status):
        if self._player and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._player.setPosition(0); self._player.play()

    def _stop_video(self):
        if self._player: self._player.stop()
        if self.video_widget: self.video_widget.hide()

    def _load_face(self, state: str):
        path, kind = get_face_info(state); self._stop_video()
        self._pixmap_actual = None
        if path and kind == "video" and _MULTIMEDIA_OK and self._player:
            self.image_label.hide(); self._fallback_label.hide(); self.video_widget.show()
            self._player.setSource(QUrl.fromLocalFile(path)); self._player.play(); return
        if path and kind == "image":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(190, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._pixmap_actual = scaled
                self.image_label.setPixmap(scaled); self.image_label.show(); self._fallback_label.hide(); return
        fallback_marks = { "normal": "月", "happy": "月", "thinking": "…", "typing": "…", "reading": "夜", "sad": "夜", "confused": "?", "error": "✕", "sleeping": "z", "sitting": "月" }
        self._fallback_label.setText(fallback_marks.get(state, "月")); self._fallback_label.show(); self.image_label.hide()

    def set_pixmap_compuesto(self, pm):
        """Muestra `pm` (el sprite girado/desplazado que compone la mascota de sprites)
        en lugar del pixmap del estado, sin cambiar de estado. `_pixmap_actual` sigue
        siendo el sprite sin tocar. None → vuelve a mostrar el del estado. No hace nada
        si el estado es un vídeo o no tiene imagen."""
        if self.image_label.isHidden() or self._pixmap_actual is None:
            return
        if pm is None or pm.isNull():
            pm = self._pixmap_actual
        self.image_label.setPixmap(pm)

    def video_activo(self) -> bool:
        """¿Se está mostrando un vídeo (pensando/escribiendo) en vez de una imagen?"""
        return self.video_widget is not None and not self.video_widget.isHidden()

    def etiqueta_flotante(self):
        """La etiqueta de estado (月 EN LÍNEA) deja de ocupar su fila: queda encima
        de la cara y la coloca quien la contiene (`state_tag.move`); la imagen y el
        vídeo usan todo el alto. La mascota de sprites la pega a la figura (su lienzo
        con margen no cabría debajo de la fila, y con la letra a más de 100 % menos)."""
        if self._tag_flotante:
            return self.state_tag
        self._tag_flotante = True
        fila = self._tag_row
        self._tag_row = None
        fila.removeWidget(self.state_tag)
        self.layout().removeItem(fila)
        fila.deleteLater()
        self.state_tag.setParent(self)
        self.state_tag.adjustSize()
        self.state_tag.show()
        self.state_tag.raise_()
        return self.state_tag

    def set_state(self, state: str, auto_revert_ms: int = 0):
        if state == self._current_state:
            # La misma cara pedida otra vez manda también en su vuelta a normal: si
            # no, una vuelta pendiente de antes (sad 6 s) pisaría la cara de arrastre.
            if auto_revert_ms > 0: self._revert_timer.start(auto_revert_ms)
            else: self._revert_timer.stop()
            return
        self._current_state = state; self._load_face(state)
        # Tinte de la etiqueta según el estado (error=rojo, normal/feliz=cyan)
        tag_color = COLORS["error"] if state == "error" else COLORS["accent"]
        self.state_tag.setText(f"月 {STATE_LABELS.get(state, 'EN LÍNEA')}")
        self.state_tag.setStyleSheet(
            f"color:{tag_color};background:{COLORS['bg']};"
            f"border:1px solid {tag_color};padding:2px 6px;"
        )
        if self._tag_flotante:
            self.state_tag.adjustSize()             # sin fila que la redimensione
            self.state_tag.raise_()
        if auto_revert_ms > 0: self._revert_timer.start(auto_revert_ms)
        else: self._revert_timer.stop()
        self.estado_cambiado.emit(state)
