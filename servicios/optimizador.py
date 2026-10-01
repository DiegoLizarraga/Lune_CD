"""
optimizador.py — Centro de optimización y limpieza para Lune CD
================================================================
Inspirado en Stacer (Linux): permite escanear y liberar espacio,
ver el consumo del sistema en vivo y cerrar procesos pesados.

SEGURIDAD (lee esto antes de añadir categorías nuevas)
------------------------------------------------------
Hay dos formas de limpiar y cada una tiene su propia red de protección:

  1. Vaciado completo de un directorio (`patrones` vacío).
     Solo se permite si el NOMBRE de la carpeta está en `_NOMBRES_VACIABLES`
     (Cache, cache2, Temp, GPUCache…). Así es imposible apuntar por error a
     una carpeta de perfil como `Mozilla/Firefox/Profiles`, que contiene
     marcadores, contraseñas y cookies.

  2. Borrado por patrón (`patrones=["thumbcache_*.db"]`).
     Se recorre el directorio pero SOLO se borran los archivos que casan con
     el glob. Las subcarpetas ni se tocan.

`_ruta_vaciable()` es el guardián: si una ruta no pasa, se ignora en silencio
y se contabiliza en `bloqueadas`. Nunca se hace `rmtree` sobre algo que no
haya pasado por ahí.

Uso típico (desde un hilo, porque escanear puede tardar):
    from servicios.optimizador import Optimizador
    opt = Optimizador()
    categorias = opt.escanear()           # lista de CategoriaLimpieza
    resultado = opt.limpiar(["temp_usuario", "papelera"])
    procesos = opt.procesos_pesados()     # top consumidores de RAM/CPU
    stats = opt.estadisticas_sistema()    # CPU/RAM/Disco en vivo
"""

import fnmatch
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Callable

try:
    import psutil
except ImportError:
    psutil = None


# ── Utilidades de formato ──────────────────────────────────────────────────────

def formatear_bytes(num: float) -> str:
    for unidad in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.1f} {unidad}"
        num /= 1024
    return f"{num:.1f} PB"


# ── Red de seguridad ───────────────────────────────────────────────────────────
# Nombres de carpeta que es seguro vaciar por completo. Todo lo demás se
# rechaza: es preferible limpiar de menos que borrarle el perfil a alguien.
_NOMBRES_VACIABLES = {
    "cache", "cache2", "caches", "cachedata", "cache_data", "cachestorage",
    "code cache", "gpucache", "shadercache", "graphitedawncache",
    "dawncache", "temp", "tmp", "tempstate", "crashpad", "startupcache",
    "thumbnails", "service worker",
}

# Carpetas que jamás deben vaciarse aunque alguien las añada por descuido.
_NOMBRES_PROHIBIDOS = {
    "profiles", "user data", "default", "documents", "documentos", "desktop",
    "escritorio", "downloads", "descargas", "pictures", "videos", "music",
    "appdata", "roaming", "local", "locallow", "users", "usuarios",
    "windows", "system32", "program files", "program files (x86)",
    "mozilla", "firefox", "google", "chrome", "microsoft", "edge",
}


def _ruta_vaciable(ruta: Path) -> bool:
    """
    ¿Es seguro borrar TODO el contenido de esta carpeta?

    Solo si su nombre es inequívocamente de caché/temporales. Esta función es
    la única puerta de entrada a `shutil.rmtree`; no la relajes sin pensarlo.
    """
    if not ruta:
        return False
    nombre = ruta.name.strip().lower()
    if not nombre or nombre in _NOMBRES_PROHIBIDOS:
        return False
    if nombre in _NOMBRES_VACIABLES:
        return True
    # Variantes tipo "Cache_Data", "cache-v2": tratamos "cache" como raíz.
    return nombre.startswith("cache") or nombre.endswith("cache")


def _perfiles(base: Path, patron: str = "*") -> List[Path]:
    """Lista subcarpetas de perfil (Chrome «Profile 1», Firefox «xxx.default»)."""
    if not base or not base.exists():
        return []
    try:
        return [p for p in base.glob(patron) if p.is_dir()]
    except OSError:
        return []


# ── Modelo de una categoría limpiable ──────────────────────────────────────────

class CategoriaLimpieza:
    def __init__(self, clave: str, nombre: str, icono: str, descripcion: str,
                 rutas: List[Path], es_papelera: bool = False,
                 patrones: Optional[List[str]] = None):
        self.clave = clave
        self.nombre = nombre
        self.icono = icono
        self.descripcion = descripcion
        self.rutas = [r for r in rutas if r]
        self.es_papelera = es_papelera
        # Si hay patrones, solo se borran los archivos que casen con ellos.
        self.patrones = patrones or []
        self.tamano = 0          # bytes calculados tras escanear
        self.archivos = 0        # número de archivos


# ── Optimizador principal ──────────────────────────────────────────────────────

class Optimizador:
    def __init__(self):
        self.es_windows = os.name == "nt"
        self.categorias: List[CategoriaLimpieza] = self._definir_categorias()

    # ── Definición de qué se puede limpiar (seguro) ────────────────────────────

    def _definir_categorias(self) -> List[CategoriaLimpieza]:
        cats: List[CategoriaLimpieza] = []
        local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
        temp_usuario = Path(tempfile.gettempdir())

        # 1) Temporales del usuario (siempre seguro)
        cats.append(CategoriaLimpieza(
            "temp_usuario", "Archivos temporales", "▸",
            "Basura que dejan los programas en tu carpeta TEMP.",
            [temp_usuario],
        ))

        if self.es_windows:
            # 2) Temporales de Windows
            win_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
            cats.append(CategoriaLimpieza(
                "temp_windows", "Temporales de Windows", "▸",
                "Temporales del sistema (puede requerir permisos).",
                [win_temp],
            ))

            # 3) Caché de miniaturas e iconos del Explorador.
            #    Solo los .db de caché: la carpeta Explorer guarda más cosas.
            if local:
                cats.append(CategoriaLimpieza(
                    "miniaturas", "Caché de miniaturas", "▸",
                    "Miniaturas e iconos que Windows regenera solo.",
                    [local / "Microsoft" / "Windows" / "Explorer"],
                    patrones=["thumbcache_*.db", "iconcache_*.db"],
                ))

            # 4) Cachés de navegadores.
            #    OJO: solo carpetas de caché de cada perfil. Nunca la raíz del
            #    perfil — ahí viven marcadores, contraseñas y cookies.
            cats.append(CategoriaLimpieza(
                "cache_navegadores", "Caché de navegadores", "▸",
                "Solo la caché de Chrome, Edge, Brave y Firefox. "
                "No toca marcadores, contraseñas ni sesiones.",
                self._rutas_cache_navegadores(local),
            ))

            # 5) Papelera de reciclaje
            cats.append(CategoriaLimpieza(
                "papelera", "Papelera de reciclaje", "▸",
                "Vacía la papelera de forma segura.",
                [], es_papelera=True,
            ))
        else:
            # Linux/macOS: caché del usuario
            home = Path.home()
            cats.append(CategoriaLimpieza(
                "cache_usuario", "Caché del usuario", "▸",
                "Caché en ~/.cache.",
                [home / ".cache"],
            ))

        return cats

    def _rutas_cache_navegadores(self, local: Optional[Path]) -> List[Path]:
        """
        Rutas de caché por perfil de cada navegador.

        Chromium guarda la caché dentro de cada perfil («Default», «Profile 1»…)
        y Firefox la tiene en LOCALAPPDATA (no en Roaming, donde está el perfil
        con los datos personales).
        """
        rutas: List[Path] = []
        if not local:
            return rutas

        chromium = [
            local / "Google" / "Chrome" / "User Data",
            local / "Microsoft" / "Edge" / "User Data",
            local / "BraveSoftware" / "Brave-Browser" / "User Data",
            local / "Chromium" / "User Data",
        ]
        for user_data in chromium:
            for perfil in _perfiles(user_data):
                # Solo perfiles reales: Default, Profile 1, Profile 2…
                if perfil.name != "Default" and not perfil.name.startswith("Profile"):
                    continue
                rutas += [
                    perfil / "Cache" / "Cache_Data",
                    perfil / "Code Cache",
                    perfil / "GPUCache",
                    perfil / "Service Worker" / "CacheStorage",
                ]

        # Firefox: <LOCALAPPDATA>/Mozilla/Firefox/Profiles/<perfil>/cache2
        ff_local = local / "Mozilla" / "Firefox" / "Profiles"
        for perfil in _perfiles(ff_local):
            rutas.append(perfil / "cache2")

        return [r for r in rutas if r.exists()]

    # ── Escaneo ────────────────────────────────────────────────────────────────

    def escanear(self, on_progreso: Optional[Callable[[str], None]] = None) -> List[CategoriaLimpieza]:
        """Calcula cuánto espacio ocupa cada categoría. Tolerante a errores."""
        for cat in self.categorias:
            if on_progreso:
                on_progreso(f"Escaneando {cat.nombre}…")
            if cat.es_papelera:
                cat.tamano, cat.archivos = self._tamano_papelera()
            else:
                total, n = 0, 0
                for ruta in cat.rutas:
                    t, c = self._tamano_dir(ruta, cat.patrones)
                    total += t
                    n += c
                cat.tamano, cat.archivos = total, n
        return self.categorias

    def _tamano_dir(self, ruta: Path, patrones: Optional[List[str]] = None) -> tuple:
        """Tamaño de un directorio. Con `patrones`, solo cuenta lo que casa."""
        total, n = 0, 0
        if not ruta or not ruta.exists():
            return 0, 0
        for raiz, _dirs, archivos in os.walk(ruta):
            for nombre in archivos:
                if patrones and not any(fnmatch.fnmatch(nombre.lower(), p.lower()) for p in patrones):
                    continue
                try:
                    total += os.path.getsize(os.path.join(raiz, nombre))
                    n += 1
                except (OSError, PermissionError):
                    continue
            if patrones:
                break  # con patrones no bajamos a subcarpetas
        return total, n

    def _tamano_papelera(self) -> tuple:
        """Tamaño aproximado de la papelera en Windows."""
        if not self.es_windows:
            return 0, 0
        total, n = 0, 0
        for letra in "CDEFGH":
            recycle = Path(f"{letra}:/$Recycle.Bin")
            if recycle.exists():
                t, c = self._tamano_dir(recycle)
                total += t
                n += c
        return total, n

    # ── Limpieza ─────────────────────────────────────────────────────────────--

    def limpiar(self, claves: List[str],
                on_progreso: Optional[Callable[[str], None]] = None) -> Dict:
        """
        Limpia las categorías indicadas por su clave.
        Devuelve {'liberado', 'archivos', 'detalle', 'errores', 'bloqueadas'}.
        `bloqueadas` son rutas que la red de seguridad rechazó.
        """
        liberado_total, archivos_total, errores = 0, 0, 0
        detalle, bloqueadas = [], []

        for cat in self.categorias:
            if cat.clave not in claves:
                continue
            if on_progreso:
                on_progreso(f"Limpiando {cat.nombre}…")

            if cat.es_papelera:
                ok = self._vaciar_papelera()
                detalle.append(f"{cat.icono} {cat.nombre}: {'vaciada' if ok else 'no disponible'}")
                if ok:
                    liberado_total += cat.tamano
                continue

            liberado_cat, archivos_cat = 0, 0
            for ruta in cat.rutas:
                liberado, n, err, bloqueada = self._limpiar_dir(ruta, cat.patrones)
                liberado_cat += liberado
                archivos_cat += n
                errores += err
                if bloqueada:
                    bloqueadas.append(str(ruta))
            liberado_total += liberado_cat
            archivos_total += archivos_cat
            detalle.append(
                f"{cat.icono} {cat.nombre}: {formatear_bytes(liberado_cat)} liberados"
            )

        return {
            "liberado": liberado_total,
            "archivos": archivos_total,
            "detalle": detalle,
            "errores": errores,
            "bloqueadas": bloqueadas,
        }

    def _limpiar_dir(self, ruta: Path, patrones: Optional[List[str]] = None) -> tuple:
        """
        Borra contenido de un directorio. Devuelve (liberado, n, errores, bloqueada).

        Con `patrones` solo se borran archivos que casen (las subcarpetas quedan
        intactas). Sin patrones se vacía la carpeta entera, pero únicamente si
        `_ruta_vaciable()` la aprueba.
        """
        liberado, n, errores = 0, 0, 0
        if not ruta or not ruta.exists() or not ruta.is_dir():
            return 0, 0, 0, False

        if patrones:
            for entrada in ruta.iterdir():
                if not entrada.is_file():
                    continue
                if not any(fnmatch.fnmatch(entrada.name.lower(), p.lower()) for p in patrones):
                    continue
                try:
                    tam = entrada.stat().st_size
                    entrada.unlink(missing_ok=True)
                    liberado += tam
                    n += 1
                except (OSError, PermissionError):
                    errores += 1
            return liberado, n, errores, False

        # Vaciado completo: solo con el visto bueno de la red de seguridad.
        if not _ruta_vaciable(ruta):
            return 0, 0, 0, True

        for entrada in ruta.iterdir():
            try:
                if entrada.is_symlink():
                    # Borra el enlace, nunca el destino.
                    entrada.unlink(missing_ok=True)
                    n += 1
                elif entrada.is_file():
                    tam = entrada.stat().st_size
                    entrada.unlink(missing_ok=True)
                    liberado += tam
                    n += 1
                elif entrada.is_dir():
                    tam, c = self._tamano_dir(entrada)
                    shutil.rmtree(entrada, ignore_errors=True)
                    liberado += tam
                    n += c
            except (OSError, PermissionError):
                # Archivo en uso → lo dejamos, no es problema
                errores += 1
                continue
        return liberado, n, errores, False

    def _vaciar_papelera(self) -> bool:
        if not self.es_windows:
            return False
        try:
            import ctypes
            # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
            flags = 0x00000001 | 0x00000002 | 0x00000004
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            return True
        except Exception:
            return False

    # ── Procesos ─────────────────────────────────────────────────────────────--

    def procesos_pesados(self, top: int = 8) -> List[Dict]:
        """Devuelve los procesos que más RAM consumen."""
        if not psutil:
            return []
        procesos = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                mem = info["memory_info"].rss if info.get("memory_info") else 0
                procesos.append({
                    "pid": info["pid"],
                    "nombre": info["name"] or "desconocido",
                    "ram": mem,
                    "ram_str": formatear_bytes(mem),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        procesos.sort(key=lambda x: x["ram"], reverse=True)
        return procesos[:top]

    def matar_proceso(self, pid: int) -> tuple:
        """Cierra un proceso por PID. Devuelve (ok, mensaje)."""
        if not psutil:
            return False, "psutil no está instalado."
        try:
            p = psutil.Process(pid)
            nombre = p.name()
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            return True, f"Cerré «{nombre}» (PID {pid})."
        except psutil.NoSuchProcess:
            return False, "Ese proceso ya no existe."
        except psutil.AccessDenied:
            return False, "Sin permisos para cerrar ese proceso (¿es del sistema?)."
        except Exception as e:
            return False, f"No pude cerrarlo: {e}"

    # ── Estadísticas en vivo ───────────────────────────────────────────────────

    @staticmethod
    def cebar_cpu() -> None:
        """Primera muestra de CPU (al abrir el monitor). cpu_percent(None) mide desde la
        llamada anterior DEL MISMO HILO: sin cebar, la primera lectura sale en 0 %."""
        if psutil:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

    def estadisticas_sistema(self) -> Dict:
        """CPU/RAM/disco sin bloquear: la CPU es la media desde la llamada anterior
        (cpu_percent(None)), así que hay que llamarla siempre desde el mismo hilo (el
        monitor del panel, en el de Qt) y cebarla al abrir (`cebar_cpu`)."""
        if not psutil:
            return {"disponible": False}
        try:
            mem = psutil.virtual_memory()
            disco = psutil.disk_usage(os.path.abspath(os.sep))
            return {
                "disponible": True,
                "cpu": psutil.cpu_percent(interval=None),
                "ram_pct": mem.percent,
                "ram_usada": formatear_bytes(mem.used),
                "ram_total": formatear_bytes(mem.total),
                "disco_pct": disco.percent,
                "disco_libre": formatear_bytes(disco.free),
                "disco_total": formatear_bytes(disco.total),
            }
        except Exception:
            return {"disponible": False}


# ── Prueba rápida ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    opt = Optimizador()
    print("== RUTAS QUE SE LIMPIARÍAN ==")
    for c in opt.categorias:
        print(f"  {c.nombre}:")
        for r in c.rutas:
            marca = "patrón" if c.patrones else ("OK" if _ruta_vaciable(r) else "BLOQUEADA")
            print(f"     [{marca}] {r}")
    print("\n== ESCANEO ==")
    for c in opt.escanear(lambda m: None):
        print(f"  {c.clave}: {formatear_bytes(c.tamano)} ({c.archivos} archivos)")
    print("\n== TOP PROCESOS ==")
    for p in opt.procesos_pesados(5):
        print(f"  {p['nombre']} (PID {p['pid']}): {p['ram_str']}")
    print("\n== SISTEMA ==")
    opt.cebar_cpu()
    import time
    time.sleep(0.5)
    print(" ", opt.estadisticas_sistema())
