"""
ui/tema_qt.py — Controlador Qt del tema de color (nucleo/tema.py).

Un único `ControlTema` por app (lo crea `montar_escritorio` y lo registra en
ServiciosEscritorio como «tema»). Lleva dos estados:

- el GUARDADO (config.json, sección `tema`);
- el VISIBLE, que es el guardado o una vista previa (`previsualizar`, sin disco:
  el deslizador de tono de la web la llama mientras se arrastra).

Cada vez que cambia el visible emite `cambio(css_json)` (el mapa de variables
para `window.luneTema`, o "null" con el cian de siempre) y se lo pasa a la
asistente (`asistente.aplicar_tema(css_json)`). Quien monta los servicios conecta
`cambio` a la web (puente → luneTema), a la bandeja (`qss_menu()`) y al menú
radial (`colores_radial()`).

`guardar` escribe en config.json con un temporizador de 400 ms: varios cambios
seguidos (presets en la bandeja, soltar el deslizador) son UNA escritura. Al
`detener()` se escribe lo pendiente.

    tema = ControlTema(config)
    tema.cambio.connect(lambda css: bandeja.aplicar_qss(tema.qss_menu()))
    tema.set_asistente(companion)            # → companion.aplicar_tema(tema.css_json())
    tema.previsualizar({"hue": 200, "preset": "personalizado"})
    tema.guardar({"hue": 200, "preset": "personalizado"})
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from nucleo import tema
from ui import tema_qss

_log = logging.getLogger("lune.tema")

RETARDO_GUARDADO_MS = 400
MAX_JSON = 4096           # vista previa / guardado desde la web: nada más grande


def escribir_claves(config: Any, cambios: Dict[Tuple[str, str], Any]) -> bool:
    """Escribe varias claves {(sección, clave): valor} de config.json de UNA vez,
    como el panel nativo (settings_panel._save): en `config.config` +
    `config.save()` (que no pisa lo que otros escribieron). Con un config sin esa
    forma (dobles de test), `config.set` por clave. True si se guardó."""
    if config is None or not cambios:
        return False
    datos = getattr(config, "config", None)
    guardar = getattr(config, "save", None)
    try:
        if isinstance(datos, dict) and callable(guardar):
            for (seccion, clave), valor in cambios.items():
                sec = datos.get(seccion)
                if not isinstance(sec, dict):
                    sec = datos[seccion] = {}
                sec[clave] = copy.deepcopy(valor)
            guardar()
            return True
        poner = getattr(config, "set", None)
        if callable(poner):
            for (seccion, clave), valor in cambios.items():
                poner(seccion, clave, copy.deepcopy(valor))
            return True
    except Exception:
        _log.exception("no pude guardar %s en config.json", sorted({s for s, _ in cambios}))
    return False


def escribir_config(config: Any, seccion: str, valores: Dict[str, Any]) -> bool:
    """`escribir_claves` para las claves de una sola sección."""
    return escribir_claves(config, {(seccion, k): v for k, v in (valores or {}).items()})


def _parcial(cfg: Any) -> Dict[str, Any]:
    """dict de la entrada (dict, JSON de la web o nombre de preset); {} si no vale."""
    if isinstance(cfg, (bytes, bytearray)):
        cfg = cfg.decode("utf-8", "replace")
    if isinstance(cfg, str):
        texto = cfg.strip()
        if len(texto) > MAX_JSON:
            return {}
        if texto.startswith("{"):
            try:
                cfg = json.loads(texto)
            except ValueError:
                return {}
        else:
            return {"preset": texto} if texto else {}
    if not isinstance(cfg, dict):
        return {}
    return {k: cfg[k] for k in tema.DEFECTO if k in cfg}


class ControlTema(QObject):
    """Tema de color vivo: vista previa sin disco, guardado diferido y reparto."""

    cambio = pyqtSignal(str)          # css_json del tema visible ("null" = cian de siempre)

    def __init__(self, config: Any = None, *, retardo_ms: int = RETARDO_GUARDADO_MS,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._guardado = tema.normalizar(config)
        self._visible = dict(self._guardado)
        self._css = tema.css_json(self._visible)
        self._pendiente = False
        self._asistente = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(retardo_ms)))
        self._timer.timeout.connect(self.guardar_ya)

    # ── Lectura ──────────────────────────────────────────────────────────────────
    def actual(self) -> Dict[str, Any]:
        """Sección `tema` normalizada de lo que se ve ahora (vista previa incluida)."""
        return dict(self._visible)

    def guardado(self) -> Dict[str, Any]:
        """Lo que hay (o habrá en ≤ 400 ms) en config.json."""
        return dict(self._guardado)

    def paleta(self) -> Dict[str, str]:
        return tema.paleta(self._visible)

    def css_json(self) -> str:
        return self._css

    def qss_menu(self) -> str:
        return tema_qss.qss_menu(self.paleta())

    def colores_radial(self) -> Dict[str, str]:
        return tema_qss.colores_radial(self.paleta())

    @property
    def previsualizando(self) -> bool:
        return self._visible != self._guardado

    @property
    def pendiente(self) -> bool:
        """¿Hay un guardado esperando al temporizador?"""
        return self._pendiente

    def estado(self) -> Dict[str, Any]:
        """Todo lo que necesita una tarjeta de ajustes: {tema, css (mapa o None),
        identidad, previsualizando, presets, sat_min, sat_max}."""
        css = json.loads(self._css)
        return {
            "tema": self.actual(), "css": css, "identidad": css is None,
            "previsualizando": self.previsualizando, "presets": tema.presets(),
            "sat_min": tema.SAT_MIN, "sat_max": tema.SAT_MAX,
        }

    # ── Cambios ──────────────────────────────────────────────────────────────────
    def _fusionar(self, cfg: Any) -> Dict[str, Any]:
        base = dict(self._visible)
        p = _parcial(cfg)
        if "hue" in p and "preset" not in p:
            base["preset"] = tema.PERSONALIZADO        # mover el tono = tema personalizado
        base.update(p)
        return tema.normalizar(base)

    def _mostrar(self, cfg: Dict[str, Any]) -> None:
        self._visible = dict(cfg)
        css = tema.css_json(self._visible)
        if css == self._css:
            return
        self._css = css
        self._a_asistente()
        self.cambio.emit(css)

    def previsualizar(self, cfg: Any) -> Dict[str, Any]:
        """Enseña `cfg` (parcial: se mezcla con lo visible) sin tocar el disco."""
        self._mostrar(self._fusionar(cfg))
        return self.actual()

    def descartar_vista(self) -> Dict[str, Any]:
        """Vuelve a lo guardado (se cerró la tarjeta sin guardar la vista previa)."""
        self._mostrar(self._guardado)
        return self.actual()

    def guardar(self, cfg: Any = None) -> Dict[str, Any]:
        """Enseña y guarda `cfg` (parcial); la escritura va a los 400 ms."""
        nuevo = self._fusionar(cfg if cfg is not None else {})
        # Lo guardado se actualiza ANTES de avisar: quien escucha `cambio` (el
        # panel nativo) lee guardado() dentro del aviso y debe ver ya lo nuevo.
        if nuevo != self._guardado:
            self._guardado = dict(nuevo)
            self._pendiente = True
            self._timer.start()
        self._mostrar(nuevo)
        return self.actual()

    def restablecer(self) -> Dict[str, Any]:
        """El tema por defecto (cian, 100 %, sin teñir amarillo ni fondos)."""
        return self.guardar(dict(tema.DEFECTO))

    def aplicar_preset(self, p: str) -> Dict[str, Any]:
        """Cambia el tono al del preset (conserva saturación y banderas). Un id
        desconocido no cambia nada."""
        pid = str(p or "").strip().lower()
        if pid not in tema.PRESETS:
            return self.actual()
        return self.guardar({"preset": pid})

    def recargar(self) -> Dict[str, Any]:
        """Relee la sección `tema` de config (la cambió otro: el panel nativo,
        patata…). Lo pendiente de este objeto se escribe antes."""
        self.guardar_ya()
        try:
            recargar = getattr(self.config, "recargar", None)
            if callable(recargar):
                recargar()
        except Exception:
            _log.debug("recargar config falló", exc_info=True)
        self._guardado = tema.normalizar(self.config)
        self._mostrar(self._guardado)
        return self.actual()

    def guardar_ya(self) -> bool:
        """Escribe ya lo pendiente. True si escribió."""
        self._timer.stop()
        if not self._pendiente:
            return False
        self._pendiente = False
        return escribir_config(self.config, "tema", self._guardado)

    # ── Asistente y ciclo de vida (contrato de controlador de ui/escritorio.py) ─────
    def set_asistente(self, v: Any) -> None:
        self._asistente = v
        self._a_asistente()

    def _a_asistente(self) -> None:
        v = self._asistente
        f = getattr(v, "aplicar_tema", None) if v is not None else None
        if not callable(f):
            return
        try:
            f(self._css)
        except RuntimeError:                       # ventana ya destruida por Qt
            self._asistente = None
        except Exception:
            _log.exception("la asistente no aceptó el tema")

    def iniciar(self) -> None:
        """Nada que arrancar: el tema se aplica al crearse y con set_asistente."""

    def detener(self) -> None:
        self.guardar_ya()
        self._asistente = None


__all__ = ("ControlTema", "escribir_claves", "escribir_config", "RETARDO_GUARDADO_MS")
