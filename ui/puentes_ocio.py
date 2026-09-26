"""
ui/puentes_ocio.py — los dos objetos «de ocio» del QWebChannel de la piel web (cortes 5 y 6).

Qué es
------
La página normal (ui_web/ui_kits/lune-desktop/index.html) ve, además de `window.lune` y
`window.luneEscritorio`, otros dos objetos del canal que registra `registrar_puentes_ocio`:

    alarmas → window.luneAlarmas   (ui/puente_alarmas.py: alarmas, temporizadores,
                                     pantalla grande y salvapantallas)
    musica  → window.luneMusica    (ui/puente_musica.py: baile con la música)

Se registran SIEMPRE en `VentanaWeb.__init__`, antes de `setUrl` (el JS solo ve lo que
estaba registrado al crear su QWebChannel), aunque los controladores de los cortes 5/6
(`ServiciosOcio`, que monta ui/montaje_ocio.montar_ocio dentro de montar_escritorio)
lleguen después, en `iniciar_servicios`. Por eso los dos puentes aceptan los servicios
tarde: `PuentesOcio.enlazar(servicios_c4)`. Sin servicios, cada ranura devuelve un estado
por defecto (y lo que es solo config se lee y se guarda igual).

Contrato:
    registrar_puentes_ocio(canal, config, servicios_c4=None) -> PuentesOcio
    PuentesOcio.alarmas / .musica            los dos QObject
    PuentesOcio.enlazar(servicios_c4 | None) toma ServiciosCorte4.ocio (o un ServiciosOcio,
                                             o nada = soltar); se apunta en
                                             servicios_c4._deshacer para soltarlos solo
                                             cuando se desmonten (cambio de interfaz)
    PuentesOcio.cerrar()                     suelta señales y registro en el canal (idempotente)

Aquí vive también lo común de los dos puentes (`PuenteOcioBase`): lectura estricta del
JSON de la página, config con `config.get/set` y señales de los controladores con
desconexión segura. Todo por duck typing y `getattr` defensivo: un controlador que falta
o que lanza nunca tumba una ranura.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject

_log = logging.getLogger("lune.puentes_ocio")

MAX_JSON = 16 * 1024                 # caracteres por payload de la página
MAX_TEXTO = 160                      # textos de alarma y temporizador

ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


# ── Utilidades puras ───────────────────────────────────────────────────────────

def _rechazar_constante(nombre: str):
    raise ValueError(f"constante no permitida: {nombre}")


def leer_json(texto: Any, tipo: type = dict) -> Any:
    """JSON de la página → objeto de `tipo`, o None si no vale (tamaño, NaN, tipo)."""
    if not isinstance(texto, str) or not texto or len(texto) > MAX_JSON:
        return None
    try:
        obj = json.loads(texto, parse_constant=_rechazar_constante)
    except (ValueError, TypeError, RecursionError):
        return None
    return obj if isinstance(obj, tipo) else None


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str)


def es_bool(v: Any) -> bool:
    return isinstance(v, bool)


def numero(v: Any) -> Optional[float]:
    """Número finito (no bool) o None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def entero(v: Any) -> Optional[int]:
    """Entero de verdad (7 o 7.0; no 7.5, ni "7", ni True) o None."""
    f = numero(v)
    if f is None or f != int(f):
        return None
    return int(f)


def acotar(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def texto_limpio(v: Any, maximo: int = MAX_TEXTO) -> str:
    """Texto para la página o para guardar: sin controles ni marcas bidi, sin espacios
    de sobra a los lados y recortado."""
    if v is None:
        return ""
    s = str(v)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    return s.strip()[:maximo]


def id_valido(v: Any) -> bool:
    return isinstance(v, str) and bool(ID_OK.match(v))


def a_dict(item: Any, campos: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """Dataclass, dict u objeto con atributos → dict (solo `campos` si es un objeto suelto)."""
    if isinstance(item, dict):
        return item
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        try:
            return dataclasses.asdict(item)
        except Exception:
            pass
    return {c: getattr(item, c) for c in campos if hasattr(item, c)}


def llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    """`obj.metodo(*args)` si existe; un fallo se registra y devuelve None."""
    if obj is None:
        return None
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("puentes_ocio: %s.%s falló", type(obj).__name__, metodo)
        return None


def controladores(servicios: Any) -> Dict[str, Any]:
    """{alarmas, grande, baile} de lo que se le dé a `enlazar`:
      · ServiciosCorte4 con `.ocio` (ServiciosOcio de montar_ocio);
      · un ServiciosOcio directamente (con .alarmas/.grande/.baile);
      · si falta alguno, el registrado en el escritorio (`escritorio.obtener(nombre)`).
    Lo que no esté es None."""
    out: Dict[str, Any] = {"alarmas": None, "grande": None, "baile": None}
    if servicios is None:
        return out
    ocio = getattr(servicios, "ocio", None)
    base = ocio if ocio is not None else servicios
    for n in out:
        out[n] = getattr(base, n, None)
    esc = getattr(servicios, "escritorio", None)
    obtener = getattr(esc, "obtener", None) if esc is not None else None
    if callable(obtener):
        for n in out:
            if out[n] is None:
                try:
                    out[n] = obtener(n)
                except Exception:
                    out[n] = None
    return out


# ── Base de los dos puentes ─────────────────────────────────────────────────────

class PuenteOcioBase(QObject):
    """Config, señales de los controladores y cierre, comunes a `alarmas` y `musica`."""

    NOMBRE = "ocio"                              # nombre en el canal (lo pisa cada puente)

    def __init__(self, config: Any = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._conexiones: List[Tuple[Any, Callable]] = []
        self._canal: Any = None
        self._cerrado = False

    # ── Config ─────────────────────────────────────────────────────────────────
    def _cfg(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        c = self.config
        if c is None:
            return defecto
        try:
            if hasattr(c, "get") and hasattr(c, "config"):
                return c.get(seccion, clave, defecto)
            if isinstance(c, dict):
                return (c.get(seccion) or {}).get(clave, defecto)
        except Exception:
            _log.exception("%s: leer config %s.%s", self.NOMBRE, seccion, clave)
        return defecto

    def _cfg_set(self, seccion: str, clave: str, valor: Any) -> bool:
        c = self.config
        if c is None:
            return False
        try:
            if hasattr(c, "set") and hasattr(c, "config"):
                c.set(seccion, clave, valor)
            elif isinstance(c, dict):
                c.setdefault(seccion, {})[clave] = valor
            else:
                return False
            return True
        except Exception:
            _log.exception("%s: guardar config %s.%s", self.NOMBRE, seccion, clave)
            return False

    def _defecto(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        """Valor de DEFAULT_CONFIG (copia si es lista o dict), o `defecto`."""
        base = getattr(self.config, "DEFAULT_CONFIG", None)
        if not isinstance(base, dict):
            try:
                from nucleo.config import Config
                base = Config.DEFAULT_CONFIG
            except Exception:
                return defecto
        v = (base.get(seccion) or {}).get(clave, defecto)
        return json.loads(json.dumps(v)) if isinstance(v, (list, dict)) else v

    def _guardar_cambios(self, seccion: str, cambios: Dict[str, Any]) -> bool:
        """Guarda solo lo que cambia (cada config.set escribe el archivo)."""
        ok = True
        for k, v in cambios.items():
            if self._cfg(seccion, k, None) != v:
                ok = self._cfg_set(seccion, k, v) and ok
        return ok

    # ── Señales de los controladores ───────────────────────────────────────────
    def _conectar(self, obj: Any, senal: str, slot: Callable) -> None:
        s = getattr(obj, senal, None) if obj is not None else None
        if s is None or not hasattr(s, "connect"):
            return
        try:
            s.connect(slot)
            self._conexiones.append((s, slot))
        except (TypeError, RuntimeError):
            _log.debug("%s: no pude conectar %s", self.NOMBRE, senal)

    def _desconectar_todo(self) -> None:
        conexiones, self._conexiones = self._conexiones, []
        for s, slot in conexiones:
            try:
                s.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def cerrar(self) -> None:
        """Suelta las señales de los controladores y el registro en el canal. Idempotente."""
        self._cerrado = True
        self._desconectar_todo()
        canal, self._canal = self._canal, None
        dereg = getattr(canal, "deregisterObject", None) if canal is not None else None
        if callable(dereg):
            try:
                dereg(self)
            except (TypeError, RuntimeError):
                pass


# ── Los dos puentes juntos ──────────────────────────────────────────────────────

class PuentesOcio:
    """Los puentes `alarmas` y `musica` ya registrados en el canal."""

    def __init__(self, alarmas: Any, musica: Any):
        self.alarmas = alarmas
        self.musica = musica
        self._servicios: Any = None
        self._enganchados: List[Any] = []        # servicios en cuyo _deshacer ya estamos
        self._cerrado = False

    def enlazar(self, servicios_c4: Any = None) -> None:
        """Da a los puentes los controladores de los cortes 5/6 (o los suelta con None).

        Acepta ServiciosCorte4 (usa su `.ocio`), un ServiciosOcio o None. Se apunta en
        `servicios_c4._deshacer`: cuando esos servicios se desmonten (cambio de interfaz
        en caliente, salir), los puentes sueltan sus controladores antes de que
        ServiciosOcio.desmontar() los borre. La página, si ya estaba cargada, recibe el
        estado nuevo por las señales de siempre."""
        if self._cerrado:
            return
        self._servicios = servicios_c4
        c = controladores(servicios_c4)
        llamar(self.alarmas, "enlazar", alarmas=c["alarmas"], grande=c["grande"])
        llamar(self.musica, "enlazar", baile=c["baile"])
        deshacer = getattr(servicios_c4, "_deshacer", None) if servicios_c4 is not None else None
        if isinstance(deshacer, list) and not any(s is servicios_c4 for s in self._enganchados):
            self._enganchados.append(servicios_c4)

            def soltar(servicios=servicios_c4) -> None:
                if self._servicios is servicios:
                    self.enlazar(None)
            deshacer.append(soltar)

    def cerrar(self) -> None:
        """Suelta controladores, señales y el registro de los dos objetos. Idempotente."""
        if self._cerrado:
            return
        self._cerrado = True
        self._servicios = None
        self._enganchados.clear()
        for p in (self.alarmas, self.musica):
            llamar(p, "cerrar")


def registrar_puentes_ocio(canal: Any, config: Any, servicios_c4: Any = None, **kw) -> PuentesOcio:
    """Crea `PuenteAlarmas` y `PuenteMusica`, los registra en `canal` (QWebChannel) como
    «alarmas» y «musica» y, si ya hay servicios, los enlaza.

    Hay que llamarlo antes de que la página cree su QWebChannel (antes de setUrl). Los
    puentes quedan como hijos del canal. `kw` (keyword-only, para los tests): `reloj`
    (epoch en s) para el de alarmas."""
    from ui.puente_alarmas import PuenteAlarmas
    from ui.puente_musica import PuenteMusica
    padre = canal if isinstance(canal, QObject) else None
    alarmas = PuenteAlarmas(config=config, parent=padre, **({"reloj": kw["reloj"]} if "reloj" in kw else {}))
    musica = PuenteMusica(config=config, parent=padre)
    reg = getattr(canal, "registerObject", None)
    if callable(reg):
        for nombre, p in (("alarmas", alarmas), ("musica", musica)):
            try:
                reg(nombre, p)
                p._canal = canal
            except Exception:
                _log.exception("puentes_ocio: no pude registrar «%s» en el canal", nombre)
    puentes = PuentesOcio(alarmas, musica)
    if servicios_c4 is not None:
        puentes.enlazar(servicios_c4)
    return puentes
