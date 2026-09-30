"""
ui/puente_musica.py — objeto `musica` del QWebChannel (window.luneMusica), cortes 5 y 6.

Lo usa la piel web normal: extra/baile.jsx (BaileCard y `LuneBaileWeb.useBaile()`, que
sidebar.jsx usa para que baile la asistente de la barra) para hablar con ControlBaile
(ui/baile_qt.py). El controlador llega tarde con `enlazar(baile=…)` (ui/puentes_ocio.py);
sin él, las ranuras devuelven un estado por defecto y la config (config_baile*, apps) se
lee y se guarda igual.

Las apps de música (baile.apps) se guardan como Mate-Engine: el nombre del programa sin
«.exe» y sin rutas («Spotify», «foobar2000»); se comparan sin mayúsculas y «empiezan por».

Ranuras (JS: el resultado llega por callback, `luneMusica.x(args…, cb)`):
    estado_json() → str        {bailando, origen (auto|manual|""), musica, app, estilo, bpm, energia,
                                auto, pausado_hasta_silencio, disponible}
    bailar(int) → bool          segundos (0 = los de por defecto; 5–300)
    parar() → bool
    config_baile() → str       {auto, umbral, apps, cambiar, cambiar_s, particulas}
    config_baile_guardar(json) → str   {ok, error, estado: config_baile}
    apps_audio() → str         JSON ["Spotify", …]: lo que suena ahora (caché del último sondeo;
                                el refresco llega por apps_cambio)
    app_permitir(str) → str    {ok, error, apps}
    app_quitar(str) → str      {ok, error, apps}
Señales:
    baile_estado(str)   JSON de estado_json()
    baile_pulso(str)    {bpm, fase, energia} (como mucho 2 por segundo: lo limita ControlBaile)
    apps_cambio(str)    JSON ["Spotify", …] (suenan ahora)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ui.puentes_ocio import PuenteOcioBase, a_dict, acotar, dump, entero, es_bool, leer_json, llamar, numero

_log = logging.getLogger("lune.puente_musica")

MAX_APPS = 30                         # baile.apps
MAX_APPS_SONANDO = 50
UMBRAL = (0.02, 0.6)
CAMBIAR_S = (5, 120)
SEGUNDOS = (5, 300)                   # nucleo/baile.py: MIN_S, MAX_S
BPM = (40.0, 250.0)
BOOLS_BAILE = ("auto", "cambiar", "particulas")
DEFECTO_BAILE = {"auto": True, "umbral": 0.05, "cambiar": False, "cambiar_s": 15, "particulas": True}
ORIGENES = ("auto", "manual")

_APP = re.compile(r"^[\w .\-()]{1,60}$")
_ESTILO = re.compile(r"^[a-z][a-z0-9_]{0,23}$")


def normalizar_app(nombre: Any, *, desde_ruta: bool = False) -> Optional[str]:
    """«  Spotify.EXE » → «Spotify». None si no es un nombre de programa: con ruta (salvo
    `desde_ruta`, para lo que da el propio backend: se queda con el archivo), comodines,
    vacío o de más de 60 caracteres."""
    if not isinstance(nombre, str) or len(nombre) > 260:
        return None
    s = nombre.strip()
    if re.search(r"[\\/:]", s):
        if not desde_ruta:
            return None
        s = re.split(r"[\\/:]", s)[-1].strip()
    if s.lower().endswith(".exe"):
        s = s[:-4].rstrip()
    if not s or not _APP.match(s) or not re.search(r"[A-Za-z0-9]", s):
        return None
    return s


def lista_apps(v: Any, *, desde_ruta: bool = False, maximo: int = MAX_APPS) -> List[str]:
    """Lista de nombres válidos, sin repetir (sin mayúsculas), en orden."""
    out: List[str] = []
    vistos = set()
    for x in (v if isinstance(v, (list, tuple)) else []):
        n = normalizar_app(x, desde_ruta=desde_ruta)
        if n and n.lower() not in vistos:
            vistos.add(n.lower())
            out.append(n)
        if len(out) >= maximo:
            break
    return out


def normalizar_pulso(obj: Any) -> Optional[Dict[str, float]]:
    """Payload de ControlBaile.pulso (JSON, dict o Pulso) → {bpm, fase, energia}."""
    if isinstance(obj, str):
        obj = leer_json(obj)
    d = a_dict(obj, ("bpm", "fase", "energia")) if obj is not None else {}
    bpm, fase, en = numero(d.get("bpm")), numero(d.get("fase")), numero(d.get("energia"))
    if bpm is None or fase is None:
        return None
    return {
        "bpm": round(acotar(bpm, *BPM), 2),
        "fase": round(fase % 1.0, 4),
        "energia": round(acotar(en if en is not None else 0.5, 0.0, 1.0), 3),
    }


class PuenteMusica(PuenteOcioBase):
    """Objeto `musica` del QWebChannel (window.luneMusica)."""

    NOMBRE = "puente_musica"

    baile_estado = pyqtSignal(str)
    baile_pulso = pyqtSignal(str)
    apps_cambio = pyqtSignal(str)

    def __init__(self, config: Any = None, *, baile: Any = None, parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._baile: Any = None
        if baile is not None:
            self.enlazar(baile=baile)

    @property
    def baile(self) -> Any:
        return self._baile

    def enlazar(self, *, baile: Any = None) -> None:
        """ControlBaile (o None: soltarlo). Reconecta sus señales y, si cambió, manda el
        estado nuevo a la página."""
        if self._cerrado:
            baile = None
        antes = self._baile
        self._desconectar_todo()
        self._baile = baile
        self._conectar(baile, "estado_cambio", self._on_estado)
        self._conectar(baile, "pulso", self._on_pulso)
        self._conectar(baile, "apps_cambio", self._on_apps)
        if baile is not antes and not self._cerrado:
            self.baile_estado.emit(self.estado_json())

    def cerrar(self) -> None:
        self._baile = None
        super().cerrar()

    # ── Señales del controlador ────────────────────────────────────────────────
    def _on_estado(self, payload: Any = None) -> None:
        obj = leer_json(payload) if isinstance(payload, str) else payload
        self.baile_estado.emit(dump(self._normalizar_estado(obj if isinstance(obj, dict) else None)))

    def _on_pulso(self, payload: Any = None) -> None:
        p = normalizar_pulso(payload)
        if p is not None:
            self.baile_pulso.emit(dump(p))

    def _on_apps(self, payload: Any = None) -> None:
        lista = leer_json(payload, list) if isinstance(payload, str) else payload
        self.apps_cambio.emit(dump(lista_apps(lista, desde_ruta=True, maximo=MAX_APPS_SONANDO)))

    # ── Estado ─────────────────────────────────────────────────────────────────
    def _normalizar_estado(self, e: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        auto_cfg = self._cfg("baile", "auto", True) is not False
        if not isinstance(e, dict):
            e = {}
        bpm = numero(e.get("bpm"))
        en = numero(e.get("energia"))
        estilo = e.get("estilo") if isinstance(e.get("estilo"), str) and _ESTILO.match(e.get("estilo")) else ""
        bailando = e.get("bailando") is True
        return {
            "bailando": bailando,
            "origen": e.get("origen") if bailando and e.get("origen") in ORIGENES else "",
            "musica": e.get("musica") is True,
            "app": normalizar_app(e.get("app") or "", desde_ruta=True) or "",
            "estilo": estilo,
            "bpm": round(acotar(bpm, *BPM), 1) if bpm else 0,
            "energia": round(acotar(en, 0.0, 1.0), 3) if en is not None else 0,
            "auto": e.get("auto") if isinstance(e.get("auto"), bool) else auto_cfg,
            "pausado_hasta_silencio": e.get("pausado_hasta_silencio") is True,
            "disponible": self._baile is not None,
        }

    @pyqtSlot(result=str)
    def estado_json(self) -> str:
        e = llamar(self._baile, "estado") if self._baile is not None else None
        return dump(self._normalizar_estado(e if isinstance(e, dict) else None))

    @pyqtSlot(int, result=bool)
    def bailar(self, segundos: int) -> bool:
        """0 = los segundos de por defecto (baile.py: DEFECTO_S); si no, 5–300."""
        if isinstance(segundos, bool) or not isinstance(segundos, int):
            return False
        if segundos != 0 and not SEGUNDOS[0] <= segundos <= SEGUNDOS[1]:
            return False
        return llamar(self._baile, "bailar", segundos or None) is True

    @pyqtSlot(result=bool)
    def parar(self) -> bool:
        return llamar(self._baile, "parar") is True

    # ── Config ─────────────────────────────────────────────────────────────────
    def _apps_config(self) -> List[str]:
        v = self._cfg("baile", "apps", None)
        if not isinstance(v, list):
            v = self._defecto("baile", "apps", []) or []
        return lista_apps(v)

    def _config_baile(self) -> Dict[str, Any]:
        umbral = numero(self._cfg("baile", "umbral", DEFECTO_BAILE["umbral"]))
        cs = numero(self._cfg("baile", "cambiar_s", DEFECTO_BAILE["cambiar_s"]))
        return {
            "auto": self._cfg("baile", "auto", True) is not False,
            "umbral": round(acotar(umbral if umbral is not None else DEFECTO_BAILE["umbral"], *UMBRAL), 3),
            "apps": self._apps_config(),
            "cambiar": self._cfg("baile", "cambiar", False) is True,
            "cambiar_s": int(acotar(cs if cs is not None else DEFECTO_BAILE["cambiar_s"], *CAMBIAR_S)),
            "particulas": self._cfg("baile", "particulas", True) is not False,
        }

    @pyqtSlot(result=str)
    def config_baile(self) -> str:
        return dump(self._config_baile())

    @pyqtSlot(str, result=str)
    def config_baile_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._config_baile()})

        if not obj or any(k not in (*BOOLS_BAILE, "umbral", "cambiar_s", "apps") for k in obj):
            return falla("Ajustes del baile no válidos.")
        cambios: Dict[str, Any] = {}
        for k in BOOLS_BAILE:
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios[k] = obj[k]
        if "umbral" in obj:
            u = numero(obj["umbral"])
            if u is None or not UMBRAL[0] <= u <= UMBRAL[1]:
                return falla(f"Umbral entre {UMBRAL[0]} y {UMBRAL[1]}.")
            cambios["umbral"] = round(u, 3)
        if "cambiar_s" in obj:
            c = entero(obj["cambiar_s"])
            if c is None or not CAMBIAR_S[0] <= c <= CAMBIAR_S[1]:
                return falla(f"Cambiar de baile entre {CAMBIAR_S[0]} y {CAMBIAR_S[1]} s.")
            cambios["cambiar_s"] = c
        if "apps" in obj:
            apps = obj["apps"]
            if not isinstance(apps, list) or len(apps) > MAX_APPS:
                return falla(f"Como mucho {MAX_APPS} apps.")
            norm = [normalizar_app(a) for a in apps]
            if any(a is None for a in norm):
                return falla("Solo nombres de programa (por ejemplo Spotify), sin rutas.")
            cambios["apps"] = lista_apps(norm)
        ok = self._guardar_cambios("baile", cambios)
        llamar(self._baile, "recargar_config")
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._config_baile()})

    # ── Apps de música ─────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def apps_audio(self) -> str:
        crudas = llamar(self._baile, "apps_sonando") if self._baile is not None else None
        return dump(lista_apps(crudas, desde_ruta=True, maximo=MAX_APPS_SONANDO))

    def _cambiar_app(self, nombre: Any, quitar: bool) -> str:
        n = normalizar_app(nombre)
        if n is None:
            return dump({"ok": False, "error": "Solo el nombre del programa (por ejemplo Spotify), sin rutas.",
                         "apps": self._apps_config()})
        actuales = self._apps_config()
        if not quitar and n.lower() not in {a.lower() for a in actuales} and len(actuales) >= MAX_APPS:
            return dump({"ok": False, "error": f"Como mucho {MAX_APPS} apps.", "apps": actuales})
        metodo = "quitar_app" if quitar else "permitir_app"
        if self._baile is not None and callable(getattr(self._baile, metodo, None)):
            r = llamar(self._baile, metodo, n)
            ok = r is not None
            return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "apps": self._apps_config()})
        if quitar:
            nuevas = [a for a in actuales if a.lower() != n.lower()]
        else:
            nuevas = actuales if n.lower() in {a.lower() for a in actuales} else actuales + [n]
        ok = nuevas == actuales or self._cfg_set("baile", "apps", nuevas)
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "apps": self._apps_config()})

    @pyqtSlot(str, result=str)
    def app_permitir(self, nombre: str) -> str:
        return self._cambiar_app(nombre, quitar=False)

    @pyqtSlot(str, result=str)
    def app_quitar(self, nombre: str) -> str:
        return self._cambiar_app(nombre, quitar=True)
