"""
servicios/modo_juego.py — ¿Hay un juego delante? Y qué hacer mientras tanto.

PARA QUÉ SIRVE
--------------
Mate-Engine no tiene detector de juegos: suelta la ventana si otra está a
pantalla completa (±2 px) y tiene un limitador de FPS y un recorte de memoria.
Lune añade un detector propio (sin hooks, sin leer memoria de nadie) para
esconder la mascota, callar la voz, bajar su prioridad y no hacer capturas
mientras juegas. Este módulo es la parte SIN Qt: la usan la app
(ui/modo_juego_qt.ControlModoJuego) y la terminal (patata).

REGLAS (cada 2 s, en este orden; la primera que acierta manda)
-------------------------------------------------------------
0. La ventana activa es de Lune (el proceso propio o sus QtWebEngineProcess):
   no hay juego (salvo forzado). Así la pantalla grande propia no cuenta.
1. QUNS (SHQueryUserNotificationState): 3 (Direct3D a pantalla completa) y 4
   (presentación) siempre; 2 (ocupado) solo con `incluir_videos` y si la propia
   Lune no está en pantalla grande o salvapantallas.
2. La ventana activa no es el escritorio, cubre SU monitor (±2 px) y no tiene
   barra de título: juego en ventana sin bordes. Con `incluir_videos=False` se
   descartan los navegadores (F11 en YouTube).
3. Su exe está en `juego.apps` (sin mayúsculas, con o sin .exe).
4. Con `rutas_juego`: la ruta del exe cae en una carpeta de juegos (Steam, Epic,
   Riot, Xbox, GOG). Abre un handle de consulta limitada del proceso ajeno
   (psutil.exe()), cacheado 60 s por pid y solo si fallan las reglas 1-3.

Histéresis: 2 lecturas positivas para entrar (≈4 s) y 3 negativas para salir
(≈6 s). `forzar(True/False)` manda sobre todo; `forzar(None)` vuelve a detectar.

SEGURIDAD (anticheat)
---------------------
Sobre procesos ajenos solo se lee: ventana activa, su rect, estilo, clase, el
QUNS, y nombre/ruta del exe con un handle de consulta limitada. La prioridad
(`aplicar_prioridad`) y el recorte de RAM (servicios/recorte_ram.py) solo tocan
los pids de `win_pantalla.pids_propios()`: el propio y sus QtWebEngineProcess.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from servicios import win_pantalla as wp

# Valores de `Lectura.motivo`
MOTIVOS = ("quns3", "quns4", "quns2", "sin_bordes", "lista", "ruta", "forzado", "")

ACCIONES = ("ocultar", "fondo", "nada")
FPS_MAX_JUEGO = 60

# Navegadores: con incluir_videos=False, su F11 no cuenta como juego sin bordes.
NAVEGADORES = frozenset({
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "vivaldi.exe",
})
# Trozos de ruta (en minúsculas) de las carpetas donde instalan juegos las tiendas.
RUTAS_JUEGO = (
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\riot games\\",
    "\\xboxgames\\",
    "\\gog galaxy\\games\\",
)
TTL_RUTA_S = 60.0
MAX_CACHE_RUTAS = 64

# Procesos del sistema que salen con ventana visible pero nunca son «la app» que
# se quiere añadir a la lista.
_NO_APPS = frozenset({
    "explorer.exe", "applicationframehost.exe", "textinputhost.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "lockapp.exe", "systemsettings.exe",
})

# Lo que vale como nombre de app: letras, números, espacio, punto, guion, paréntesis.
# Nada de rutas (\ / :), comodines ni comillas.
_PATRON_APP = re.compile(r"[\w .\-()]{1,80}")

# Valores por defecto de la sección `juego` (los mismos que nucleo/config.py).
DEFECTOS_JUEGO: Dict[str, object] = {
    "activo": True,
    "accion": "ocultar",
    "fps": 0,
    "apps": [],
    "rutas_juego": True,
    "incluir_videos": True,
    "prioridad_baja": True,
    "recortar_ram": True,
    "silenciar": True,
}


# ── Tipos ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lectura:
    """Una lectura del detector: ¿juego?, por qué regla y el exe de la ventana."""
    juego: bool
    motivo: str          # quns3 | quns4 | quns2 | sin_bordes | lista | ruta | forzado | ""
    exe: str = ""


@dataclass(frozen=True)
class PlanJuego:
    """Qué hacer mientras dura el modo juego (sale de la config con `plan()`)."""
    accion: str                  # ocultar · fondo · nada
    fps: int                     # fps de la mascota (0 = pausada)
    silenciar_voz: bool
    prioridad_baja: bool
    recortar_ram: bool
    pausar_atajos: bool
    parar_comentarios: bool = True
    bloquear_capturas: bool = True
    parar_aburrimiento: bool = True


# ── Config ────────────────────────────────────────────────────────────────────

def _seccion(config, nombre: str) -> dict:
    """La sección `nombre` de un nucleo.config.Config o de un dict de secciones."""
    if config is None:
        return {}
    datos = getattr(config, "config", None)
    if isinstance(datos, dict):
        sec = datos.get(nombre)
    elif isinstance(config, dict):
        sec = config.get(nombre)
    else:
        sec = None
    return dict(sec) if isinstance(sec, dict) else {}


def ajustes_juego(config) -> dict:
    """La sección `juego` con sus valores por defecto y tipos saneados. Acepta un
    Config, un dict de secciones o la propia sección `juego` como dict."""
    if isinstance(config, dict) and "juego" not in config and any(k in config for k in DEFECTOS_JUEGO):
        crudo = dict(config)
    else:
        crudo = _seccion(config, "juego")
    j = dict(DEFECTOS_JUEGO)
    for clave in ("activo", "rutas_juego", "incluir_videos", "prioridad_baja", "recortar_ram", "silenciar"):
        if clave in crudo:
            j[clave] = bool(crudo[clave])
    accion = crudo.get("accion", j["accion"])
    j["accion"] = accion if accion in ACCIONES else "ocultar"
    try:
        fps = int(crudo.get("fps", 0))
    except (TypeError, ValueError):
        fps = 0
    j["fps"] = max(0, min(FPS_MAX_JUEGO, fps))
    apps = crudo.get("apps", [])
    j["apps"] = [a for a in (normalizar_app(x) for x in apps) if a] if isinstance(apps, (list, tuple)) else []
    return j


def normalizar_app(nombre: str) -> Optional[str]:
    """«Game.EXE» → «game.exe»; «Game» → «game.exe». None si no es un nombre de
    ejecutable válido (rutas, comodines, vacío, más de 80 caracteres…)."""
    if not isinstance(nombre, str):
        return None
    n = nombre.strip()
    if not n or not _PATRON_APP.fullmatch(n):
        return None
    n = n.lower()
    if not n.strip(". "):
        return None
    if not n.endswith(".exe"):
        n += ".exe"
    return n


def plan(config) -> PlanJuego:
    """El plan del modo juego según la config (acción inválida → «ocultar»; fps 0..60)."""
    j = ajustes_juego(config)
    atajos = _seccion(config, "atajos")
    return PlanJuego(
        accion=str(j["accion"]),
        fps=int(j["fps"]),
        silenciar_voz=bool(j["silenciar"]),
        prioridad_baja=bool(j["prioridad_baja"]),
        recortar_ram=bool(j["recortar_ram"]),
        pausar_atajos=bool(atajos.get("pausar_en_juegos", True)),
    )


# ── Caché de rutas (regla 4) ──────────────────────────────────────────────────

class CacheRutas:
    """Ruta del exe por pid, `ttl` s: la regla de rutas no abre un handle del
    proceso del juego en cada lectura, sino una vez por minuto como mucho."""

    def __init__(self, ttl: float = TTL_RUTA_S, reloj: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self._reloj = reloj
        self._datos: Dict[int, Tuple[float, str]] = {}

    def ruta(self, pid: int, api) -> str:
        ahora = self._reloj()
        hit = self._datos.get(pid)
        if hit is not None and ahora - hit[0] < self.ttl:
            return hit[1]
        ruta = wp.ruta_proceso(pid, api)
        if len(self._datos) >= MAX_CACHE_RUTAS:
            self._datos = {p: v for p, v in self._datos.items() if ahora - v[0] < self.ttl}
            if len(self._datos) >= MAX_CACHE_RUTAS:
                self._datos.clear()
        self._datos[pid] = (ahora, ruta)
        return ruta


def _es_ruta_de_juego(ruta: str) -> bool:
    r = (ruta or "").replace("/", "\\").lower()
    return bool(r) and any(t in r for t in RUTAS_JUEGO)


# ── Una lectura ───────────────────────────────────────────────────────────────

def evaluar_una_vez(cfg: dict, api=None, *, pids=None, lune_a_pantalla_completa: bool = False,
                    cache: Optional[CacheRutas] = None) -> Lectura:
    """Aplica las reglas 0-4 una vez (sin histéresis). `cfg`: la config (o su
    sección `juego`). `pids`: un win_pantalla.PidsLune (para la regla 0)."""
    j = ajustes_juego(cfg)
    if not j["activo"]:
        return Lectura(False, "")
    api = api or wp.api_defecto()
    if pids is None:
        pids = wp.PidsLune(api)
    info = wp.ventana_primer_plano(api)
    exe = (info.exe or "").lower() if info is not None else ""
    # 0. La ventana activa es de Lune: no hay juego.
    try:
        if info is not None and pids.contiene(info.pid):
            return Lectura(False, "", exe)
    except Exception:
        pass
    # 1. QUNS.
    quns = wp.estado_notificaciones(api)
    if quns in (wp.QUNS_RUNNING_D3D_FULL_SCREEN, wp.QUNS_PRESENTATION_MODE):
        return Lectura(True, f"quns{quns}", exe)
    if quns == wp.QUNS_BUSY and wp.quns_indica_juego(quns, j["incluir_videos"], lune_a_pantalla_completa):
        return Lectura(True, "quns2", exe)
    if info is None:
        return Lectura(False, "")
    # 2. Sin bordes cubriendo su monitor.
    if (not wp.es_escritorio(info) and wp.es_pantalla_completa(info, tol=2)
            and not wp.tiene_titulo(info)):
        if j["incluir_videos"] or exe not in NAVEGADORES:
            return Lectura(True, "sin_bordes", exe)
    # 3. La lista del usuario.
    if exe:
        n = normalizar_app(exe)
        if n and n in j["apps"]:
            return Lectura(True, "lista", exe)
    # 4. Carpetas de juegos (solo si lo anterior falló).
    if j["rutas_juego"] and info.pid and not wp.es_escritorio(info):
        ruta = cache.ruta(int(info.pid), api) if cache is not None else wp.ruta_proceso(int(info.pid), api)
        if _es_ruta_de_juego(ruta):
            return Lectura(True, "ruta", exe)
    return Lectura(False, "", exe)


# ── Detector con histéresis ───────────────────────────────────────────────────

class DetectorJuego:
    """Lecturas cada INTERVALO_S con histéresis: ENTRAR positivas seguidas para
    entrar y SALIR negativas seguidas para salir. `forzar()` manda. Sin Qt."""

    ENTRAR, SALIR, INTERVALO_S = 2, 3, 2.0

    def __init__(self, config, api=None, *, pids=None,
                 lune_a_pantalla_completa: Callable[[], bool] = lambda: False,
                 cache: Optional[CacheRutas] = None):
        self.config = config
        self.api = api
        self._pids = pids
        self._lune_pc = lune_a_pantalla_completa
        self._cache = cache if cache is not None else CacheRutas()
        self._activo = False
        self._motivo = ""
        self._exe = ""
        self._forzado: Optional[bool] = None
        self._positivas = 0
        self._negativas = 0

    @property
    def pids(self):
        if self._pids is None:
            self._pids = wp.PidsLune(self.api or wp.api_defecto())
        return self._pids

    def forzar(self, on: Optional[bool]) -> None:
        """True/False: modo juego a mano (manda sobre las reglas); None: detectar."""
        self._forzado = None if on is None else bool(on)
        self._positivas = self._negativas = 0

    @property
    def forzado(self) -> Optional[bool]:
        return self._forzado

    def detectando(self) -> bool:
        """¿Hace falta leer la pantalla? (config `juego.activo` o forzado)."""
        return self._forzado is not None or bool(ajustes_juego(self.config)["activo"])

    def evaluar(self) -> Tuple[bool, bool, str]:
        """Una lectura. Devuelve (cambió, activo, motivo)."""
        antes = self._activo
        if self._forzado is not None:
            self._activo = self._forzado
            self._motivo = "forzado" if self._forzado else ""
            if not self._forzado:
                self._exe = ""
            return (self._activo != antes, self._activo, self._motivo)
        if not ajustes_juego(self.config)["activo"]:
            # Detector apagado: sale ya (sin esperar a la histéresis).
            self._positivas = self._negativas = 0
            self._activo, self._motivo, self._exe = False, "", ""
            return (antes, False, "")
        try:
            pc = bool(self._lune_pc())
        except Exception:
            pc = False
        try:
            lectura = evaluar_una_vez(self.config, self.api, pids=self.pids,
                                      lune_a_pantalla_completa=pc, cache=self._cache)
        except Exception:
            lectura = Lectura(False, "")
        if lectura.juego:
            self._positivas += 1
            self._negativas = 0
            if not self._activo and self._positivas >= self.ENTRAR:
                self._activo = True
            if self._activo:
                self._motivo, self._exe = lectura.motivo, lectura.exe
        else:
            self._negativas += 1
            self._positivas = 0
            if self._activo and self._negativas >= self.SALIR:
                self._activo, self._motivo, self._exe = False, "", ""
        return (self._activo != antes, self._activo, self._motivo)

    @property
    def activo(self) -> bool:
        return self._activo

    def estado(self) -> dict:
        return {"activo": self._activo, "motivo": self._motivo,
                "forzado": self._forzado, "exe": self._exe}


# ── Prioridad del proceso (solo Lune) ─────────────────────────────────────────

_PREVIAS: Dict[int, int] = {}       # pid → prioridad antes de bajarla
_LOCK_PRIORIDAD = threading.Lock()


def aplicar_prioridad(baja: bool, *, psutil_mod=None, pids=None) -> int:
    """
    Baja (BELOW_NORMAL) o restaura la prioridad del proceso de Lune y de sus
    QtWebEngineProcess. SOLO los pids de `win_pantalla.pids_propios(pids)`: nunca
    el juego ni otro proceso. Al bajar guarda la prioridad previa de cada uno y al
    restaurar la devuelve (los hijos que nacieron con la baja vuelven a normal).
    Devuelve cuántos procesos cambió.
    """
    ps = psutil_mod
    if ps is None:
        try:
            import psutil as ps
        except Exception:
            return 0
    objetivos = wp.pids_propios(pids, ps)
    bajo = getattr(ps, "BELOW_NORMAL_PRIORITY_CLASS", 10)
    normal = getattr(ps, "NORMAL_PRIORITY_CLASS", 0)
    hechos = 0
    with _LOCK_PRIORIDAD:
        for pid in objetivos:
            try:
                proc = ps.Process(pid)
                if baja:
                    actual = proc.nice()
                    if pid not in _PREVIAS:
                        _PREVIAS[pid] = actual
                    if actual != bajo:
                        proc.nice(bajo)
                    hechos += 1
                else:
                    previa = _PREVIAS.pop(pid, None)
                    if previa is None:
                        if proc.nice() == bajo:        # nació con la baja (hijo nuevo)
                            proc.nice(normal)
                            hechos += 1
                        continue
                    proc.nice(previa)
                    hechos += 1
            except Exception:
                continue
        if not baja:
            _PREVIAS.clear()                           # los que ya no existen
    return hechos


# ── Apps con ventana (para «Añadir app») ──────────────────────────────────────

def apps_con_ventana(api=None, *, pids=None) -> List[str]:
    """Exes (normalizados, sin repetir, ordenados) con alguna ventana visible con
    título, sin los de Lune ni los del shell de Windows."""
    api = api or wp.api_defecto()
    if pids is None:
        pids = wp.PidsLune(api)
    vistos = set()
    for v in wp.ventanas_visibles(api):
        try:
            if not v.pid or pids.contiene(v.pid):
                continue
            n = normalizar_app(api.nombre_proceso(v.pid) or "")
        except Exception:
            continue
        if n and n not in _NO_APPS:
            vistos.add(n)
    return sorted(vistos)
