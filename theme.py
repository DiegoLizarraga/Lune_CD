"""
theme.py — Sistema visual "Shibuya Punk" de Lune CD.
Paleta, tipografía y metadatos de proveedores. Centraliza el estilo
para que todos los módulos compartan el mismo look (cyan/azul eléctrico
sobre tinta Tokyo-night, pop amarillo ácido, geometría afilada).

Adaptado del Design System "Lune CD — Shibuya Punk" a las limitaciones
de Qt (sin clip-path/box-shadow/webfonts): esquinas casi rectas con
bordes neón gruesos, y fuentes con fallback a las del sistema.
"""
import datos

APP_VERSION = "8.0"

# ─────────────────────────────────────────────────────────────────────────────
#  TIPOGRAFÍA
#  Display: Chakra Petch · Body: Space Grotesk · Data: Space Mono · JP: Noto Sans JP
#  Si no están instaladas, main.py registra sustituciones a fuentes del sistema.
# ─────────────────────────────────────────────────────────────────────────────
FONT_DISPLAY = "Chakra Petch"   # encabezados, en MAYÚSCULAS con tracking
FONT_BODY    = "Space Grotesk"  # texto / UI
FONT_MONO    = "Space Mono"     # datos, modelos, timestamps, estado
FONT_JP      = "Noto Sans JP"   # acentos katakana
FONT_EMOJI   = "Segoe UI Emoji"

# Fallbacks si la fuente de diseño no está instalada en el sistema
FONT_FALLBACKS = {
    FONT_DISPLAY: "Segoe UI",
    FONT_BODY:    "Segoe UI",
    FONT_MONO:    "Consolas",
    FONT_JP:      "Yu Gothic UI",
}

# ─────────────────────────────────────────────────────────────────────────────
#  COLORES — Shibuya Punk / Grind Fiction
#  (las claves se mantienen para no romper el resto de la app; cambian los hex)
# ─────────────────────────────────────────────────────────────────────────────
COLORS = {
    # ── Base: tinta Tokyo-at-night ──
    "bg":           "#080B16",   # ink-900 · fondo app
    "bg_alt":       "#0B0F1E",   # ink-850
    "surface":      "#0F1424",   # ink-800
    "surface2":     "#141B30",   # ink-700
    "surface3":     "#1B2440",   # ink-600 · hover
    "border":       "#2E3D66",   # ink-400
    "border2":      "#415379",   # ink-300 · divider bright

    # ── Texto cool ──
    "text":         "#EAF1FF",   # paper
    "text_muted":   "#97A6C4",   # gray-300
    "text_dim":     "#6E7D9E",   # gray-400

    # ── Señal primaria: cyan eléctrico (Local / live) ──
    "accent":       "#00E5FF",   # cyan-500
    "accent2":      "#36ECFF",   # cyan-400
    "cyan":         "#00E5FF",
    "cyan_dark":    "#0091AB",   # cyan-700

    # ── Señal secundaria: azul eléctrico (Nube / usuario) ──
    "blue":         "#1E55FF",   # blue-500
    "blue_dark":    "#0E2FA8",   # blue-700
    "blue_soft":    "#3D74FF",   # blue-400

    # ── Pop graffiti: amarillo ácido ──
    "yellow":       "#FFE000",   # yellow-500
    "yellow_dark":  "#E6C200",

    # ── Proveedor Local (cyan) — alias usados por la UI antigua ──
    "ollama":       "#00E5FF",
    "ollama_dark":  "#0091AB",
    # ── Proveedor Nube / Telegram (azul) ──
    "telegram":     "#3D74FF",
    "telegram_dark":"#0E2FA8",

    # ── Semánticos ──
    "success":      "#00E5FF",   # cyan
    "error":        "#FF3B5C",   # red-500
    "warning":      "#FFE000",   # yellow

    # ── Chat ──
    "user_bubble":  "#1E55FF",   # relleno azul eléctrico (usuario)
    "bot_bubble":   "#0F1424",   # superficie tinta (Lune)
    "scrollbar":    "#232F52",   # ink-500
}


def _get_system_prompt():
    return datos.get_personaje(datos.get_bot().get("personaje_default", "Lune")).get(
        "systemPrompt", "Eres Lune, una asistente virtual."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  PROVEEDORES — Nube = azul eléctrico · Local = cyan eléctrico (sin púrpura)
# ─────────────────────────────────────────────────────────────────────────────
PROVIDER_META = {
    "openrouter": {
        "label": "LUNE AI · NUBE",
        "icon": "◇",
        "svg": "cloud",
        "color": COLORS["blue_soft"],
        "dark": COLORS["blue_dark"],
        "desc": "Enrutamiento inteligente",
        "system": _get_system_prompt,
    },
    "ollama": {
        "label": "LUNE AI · LOCAL",
        "icon": "◆",
        "svg": "cpu",
        "color": COLORS["cyan"],
        "dark": COLORS["cyan_dark"],
        "desc": "Offline · sin red",
        "system": _get_system_prompt,
    },
}
