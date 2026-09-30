"""
nucleo/tema.py — Tema de color de Lune («Menu Customizations» de Mate-Engine).

Mate-Engine recolorea su interfaz con `ThemeManager.Adjust`: pasa cada color a
HSV, suma un desplazamiento de tono (`h = (h + hue) % 1`), multiplica la
saturación (`s = clamp01(s · saturation)`, con saturation en 0–2) y conserva el
brillo (V) y el alfa. Aquí se aplica la MISMA fórmula, una sola vez y en Python,
a los tokens de color de Lune (ui_web/tokens/colors.css):

- señal (cian y azul eléctrico): siempre;
- pop (amarillo ácido): solo con `tenir_pop` (con Magenta el amarillo acabaría
  turquesa, así que por defecto se queda como está);
- fondo (tinta): solo con `tenir_fondo`.

No se usa `filter: hue-rotate` en la web: recolorearía también a la asistente y
cuesta GPU. La paleta calculada llega a cada sitio en su formato:

- web y páginas de la asistente: `css_json(cfg)` → mapa de variables CSS
  `{"--cyan-500": "#…", "--cyan-500-rgb": "r g b", …}` para `window.luneTema`
  (ui_web/tema.js); "null" si el tema es la identidad (no se toca nada);
- menús Qt (bandeja y radial): ui/tema_qss.py a partir de `paleta(cfg)`;
- interfaz nativa: `colores_nativos(paleta)` → claves de ui/theme.COLORS
  (ui.theme.aplicar_tema, al arrancar);
- modo patata: `ansi(hex)` en truecolor.

La sección `tema` de config.json es {"preset", "hue" (grados), "saturacion"
(0–2), "tenir_pop", "tenir_fondo"}. Con un preset, el tono sale de PRESETS y
`hue` solo refleja ese valor en grados; con "personalizado" manda `hue`.

Sin Qt ni disco: se prueba en tests/test_tema.py.
"""
from __future__ import annotations

import colorsys
import json
import math
import re
from typing import Any, Dict, List, Mapping, Tuple

# ── Presets (tono en vueltas: 0–1, como el deslizador de Mate-Engine) ───────────
PRESETS: Dict[str, float] = {
    "cian": 0.000,
    "magenta_mate": 0.316,
    "violeta": 0.233,
    "rojo_neon": 0.455,
    "ambar": 0.594,
    "verde_acido": 0.816,
}
PERSONALIZADO = "personalizado"
ETIQUETAS: Dict[str, str] = {
    "cian": "Cian",
    "magenta_mate": "Magenta Mate",
    "violeta": "Violeta",
    "rojo_neon": "Rojo neón",
    "ambar": "Ámbar",
    "verde_acido": "Verde ácido",
    PERSONALIZADO: "Personalizado",
}
SAT_MIN, SAT_MAX = 0.0, 2.0          # SetSaturation de ME: Mathf.Clamp(value, 0, 2)
DEFECTO: Dict[str, Any] = {
    "preset": "cian", "hue": 0.0, "saturacion": 1.0, "tenir_pop": False, "tenir_fondo": False,
}

# ── Tokens base: copia de ui_web/tokens/colors.css (tests/test_tema.py lo compara) ──
BASE: Dict[str, str] = {
    # señal primaria: cian eléctrico
    "cyan-300": "#7DF5FF", "cyan-400": "#36ECFF", "cyan-500": "#00E5FF",
    "cyan-600": "#00BEDB", "cyan-700": "#0091AB",
    # señal secundaria: azul eléctrico
    "blue-300": "#6E9BFF", "blue-400": "#3D74FF", "blue-500": "#1E55FF",
    "blue-600": "#1340DB", "blue-700": "#0E2FA8",
    # pop: amarillo ácido
    "yellow-300": "#FFF27A", "yellow-400": "#FFE839", "yellow-500": "#FFE000",
    "yellow-600": "#E6C200",
    # fondo: tinta
    "ink-950": "#05070F", "ink-900": "#080B16", "ink-850": "#0B0F1E", "ink-800": "#0F1424",
    "ink-700": "#141B30", "ink-600": "#1B2440", "ink-500": "#232F52", "ink-400": "#2E3D66",
    "ink-300": "#415379",
}
GRUPOS: Dict[str, Tuple[str, ...]] = {
    "senal": tuple(t for t in BASE if t.startswith(("cyan-", "blue-"))),
    "pop": tuple(t for t in BASE if t.startswith("yellow-")),
    "fondo": tuple(t for t in BASE if t.startswith("ink-")),
}

# ── Claves de ui/theme.COLORS que salen de cada token (sus hex son los de BASE) ──
NATIVOS_SENAL: Dict[str, str] = {
    "accent": "cyan-500", "accent2": "cyan-400", "cyan": "cyan-500", "cyan_dark": "cyan-700",
    "blue": "blue-500", "blue_dark": "blue-700", "blue_soft": "blue-400",
    "ollama": "cyan-500", "ollama_dark": "cyan-700",
    "telegram": "blue-400", "telegram_dark": "blue-700",
    "success": "cyan-500", "user_bubble": "blue-500",
}
NATIVOS_POP: Dict[str, str] = {"yellow": "yellow-500", "yellow_dark": "yellow-600", "warning": "yellow-500"}
NATIVOS_FONDO: Dict[str, str] = {
    "bg": "ink-900", "bg_alt": "ink-850", "surface": "ink-800", "surface2": "ink-700",
    "surface3": "ink-600", "border": "ink-400", "border2": "ink-300",
    "bot_bubble": "ink-800", "scrollbar": "ink-500",
}

_HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
_EPS = 1e-9


# ── Utilidades ─────────────────────────────────────────────────────────────────
def _num(v: Any, defecto: float) -> float:
    if isinstance(v, bool) or v is None:
        return defecto
    try:
        f = float(v)
    except (TypeError, ValueError):
        return defecto
    return f if math.isfinite(f) else defecto


def _si(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "si", "sí", "on", "yes")
    return False


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def canales(hex_: str) -> Tuple[int, ...]:
    """«#00E5FF» → (0, 229, 255); con alfa «#00E5FF80» → (0, 229, 255, 128).
    Acepta #RGB, #RRGGBB y #RRGGBBAA (con o sin «#»). ValueError si no es un color."""
    m = _HEX.fullmatch(str(hex_ or "").strip())
    if not m:
        raise ValueError(f"color no válido: {hex_!r}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))


def _a_hex(valores) -> str:
    return "#" + "".join(f"{int(v):02X}" for v in valores)


def rgb_css(hex_: str) -> str:
    """«#00E5FF» → «0 229 255» (el formato de los canales --x-rgb de colors.css)."""
    return " ".join(str(c) for c in canales(hex_)[:3])


def _seccion(cfg: Any) -> Dict[str, Any]:
    """La sección `tema` venga como venga: nucleo.config.Config, el config.json
    entero, la propia sección, o solo el nombre de un preset (patata /tema)."""
    if cfg is None:
        return {}
    if isinstance(cfg, str):
        return {"preset": cfg}
    if isinstance(cfg, Mapping):
        t = cfg.get("tema")
        return dict(t) if isinstance(t, Mapping) else dict(cfg)
    datos = getattr(cfg, "config", None)                   # nucleo.config.Config
    if isinstance(datos, Mapping):
        t = datos.get("tema")
        return dict(t) if isinstance(t, Mapping) else {}
    get = getattr(cfg, "get", None)
    if callable(get):
        res = {}
        for clave in DEFECTO:
            try:
                v = get("tema", clave, None)
            except Exception:
                v = None
            if v is not None:
                res[clave] = v
        return res
    return {}


# ── Configuración ──────────────────────────────────────────────────────────────
def normalizar(cfg: Any = None) -> Dict[str, Any]:
    """Sección `tema` completa y válida.

    - preset desconocido → "cian"; sin preset pero con `hue` ≠ 0 → "personalizado";
    - con preset, `hue` = el tono del preset en grados (para el deslizador);
    - `hue` en [0, 360), `saturacion` en [0, 2], banderas como bool.
    """
    s = _seccion(cfg)
    preset = str(s.get("preset") or "").strip().lower()
    hue = _num(s.get("hue"), 0.0)
    if preset not in PRESETS and preset != PERSONALIZADO:
        preset = PERSONALIZADO if (not preset and hue % 360.0) else "cian"
    if preset in PRESETS:
        hue = PRESETS[preset] * 360.0
    hue = round(hue % 360.0, 2) % 360.0
    sat = round(_clamp(_num(s.get("saturacion"), 1.0), SAT_MIN, SAT_MAX), 3)
    return {
        "preset": preset,
        "hue": hue,
        "saturacion": sat,
        "tenir_pop": _si(s.get("tenir_pop", False)),
        "tenir_fondo": _si(s.get("tenir_fondo", False)),
    }


def tono(cfg: Any = None) -> float:
    """Desplazamiento de tono en vueltas [0, 1): el del preset o `hue`/360."""
    n = normalizar(cfg)
    if n["preset"] in PRESETS:
        return PRESETS[n["preset"]] % 1.0
    return (n["hue"] / 360.0) % 1.0


def _es_identidad(t: float, sat: float) -> bool:
    t = t % 1.0
    return (t < _EPS or t > 1.0 - _EPS) and abs(sat - 1.0) < _EPS


def es_identidad(cfg: Any = None) -> bool:
    """True si el tema deja todos los colores como están (el cian de siempre)."""
    return _es_identidad(tono(cfg), normalizar(cfg)["saturacion"])


# ── La fórmula (ThemeManager.Adjust de Mate-Engine) ─────────────────────────────
def ajustar(hex_: str, tono: float, sat: float) -> str:
    """RGB → HSV, h = (h + tono) mod 1, s = clamp01(s · sat), conserva V y alfa.

    `tono` en vueltas (0–1, da la vuelta: 1.25 = 0.25), `sat` multiplicador (0–2).
    Devuelve el color en mayúsculas con el mismo formato (#RRGGBB o #RRGGBBAA).
    Con tono 0 y saturación 1 devuelve el mismo color, sin pasar por HSV.
    """
    c = canales(hex_)
    t = _num(tono, 0.0)
    s_mult = _clamp(_num(sat, 1.0), SAT_MIN, SAT_MAX)
    if _es_identidad(t, s_mult):
        return _a_hex(c)
    r, g, b = (v / 255.0 for v in c[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + t) % 1.0
    s = _clamp(s * s_mult, 0.0, 1.0)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    rgb = [int(_clamp(x, 0.0, 1.0) * 255.0 + 0.5) for x in (r, g, b)]
    return _a_hex(rgb + list(c[3:]))


def paleta(cfg: Any = None) -> Dict[str, str]:
    """Token → hex para todos los tokens de BASE (los que no se tiñen, tal cual)."""
    n = normalizar(cfg)
    t, sat = tono(n), n["saturacion"]
    if _es_identidad(t, sat):
        return dict(BASE)
    tenir = set(GRUPOS["senal"])
    if n["tenir_pop"]:
        tenir.update(GRUPOS["pop"])
    if n["tenir_fondo"]:
        tenir.update(GRUPOS["fondo"])
    return {tok: (ajustar(hx, t, sat) if tok in tenir else hx) for tok, hx in BASE.items()}


def variables_css(pal: Mapping[str, str]) -> Dict[str, str]:
    """Variables CSS de los tokens que cambian respecto a BASE: «--x» (hex) y
    «--x-rgb» («r g b», el canal de colors.css). Vacío si la paleta es la base."""
    res: Dict[str, str] = {}
    for tok in BASE:
        hx = pal.get(tok)
        if not hx:
            continue
        hx = _a_hex(canales(hx)[:3])
        if hx == BASE[tok]:
            continue
        res[f"--{tok}"] = hx
        res[f"--{tok}-rgb"] = rgb_css(hx)
    return res


def css_json(cfg: Any = None) -> str:
    """JSON para `window.luneTema(…)`: el mapa de variables, o "null" si el tema
    es la identidad (la página quita lo que hubiera y se queda con colors.css)."""
    if es_identidad(cfg):
        return "null"
    variables = variables_css(paleta(cfg))
    if not variables:
        return "null"
    return json.dumps(variables, sort_keys=True, separators=(",", ":"))


def colores_nativos(pal: Mapping[str, str]) -> Dict[str, str]:
    """Claves de acento de ui/theme.COLORS con su color de la paleta.

    Siempre las de la señal (cian/azul); las del amarillo solo si la paleta tiñe
    el pop, y las de fondo solo si tiñe la tinta. Nunca texto, grises ni el rojo
    de error. Con la paleta base, los valores son los de COLORS de siempre.
    """
    def color(tok: str) -> str:
        v = pal.get(tok) or BASE[tok]
        return _a_hex(canales(v)[:3])

    res = {clave: color(tok) for clave, tok in NATIVOS_SENAL.items()}
    for grupo, claves in (("pop", NATIVOS_POP), ("fondo", NATIVOS_FONDO)):
        if any(color(t) != BASE[t] for t in GRUPOS[grupo]):
            res.update({clave: color(tok) for clave, tok in claves.items()})
    return res


def ansi(hex_: str, fondo: bool = False) -> str:
    """Secuencia ANSI truecolor para la consola (modo patata):
    «\\x1b[38;2;R;G;Bm» (texto) o «\\x1b[48;2;R;G;Bm» (fondo)."""
    r, g, b = canales(hex_)[:3]
    return f"\x1b[{48 if fondo else 38};2;{r};{g};{b}m"


def presets() -> List[Dict[str, Any]]:
    """Presets para las interfaces: [{id, etiqueta, tono, hue, muestra}], en orden.
    `muestra` es el cian-500 teñido con ese preset."""
    return [
        {"id": pid, "etiqueta": ETIQUETAS.get(pid, pid), "tono": t, "hue": round(t * 360.0, 2),
         "muestra": ajustar(BASE["cyan-500"], t, 1.0)}
        for pid, t in PRESETS.items()
    ]


__all__ = (
    "PRESETS", "PERSONALIZADO", "ETIQUETAS", "DEFECTO", "BASE", "GRUPOS", "SAT_MIN", "SAT_MAX",
    "NATIVOS_SENAL", "NATIVOS_POP", "NATIVOS_FONDO",
    "canales", "rgb_css", "normalizar", "tono", "es_identidad", "ajustar", "paleta",
    "variables_css", "css_json", "colores_nativos", "ansi", "presets",
)
