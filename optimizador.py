"""
optimizador.py — Centro de optimización y limpieza para Lune CD
================================================================
Inspirado en Stacer (Linux): permite escanear y liberar espacio,
ver el consumo del sistema en vivo y cerrar procesos pesados.

Todo es SEGURO por diseño:
  • Solo toca directorios temporales/caché conocidos.
  • Ignora archivos en uso (no rompe nada).
  • Nunca borra documentos del usuario.
  • La papelera se vacía con la API oficial de Windows.

Uso típico (desde un hilo, porque escanear puede tardar):
    from optimizador import Optimizador
    opt = Optimizador()
    categorias = opt.escanear()           # lista de CategoriaLimpieza
    resultado = opt.limpiar(["temp_usuario", "papelera"])
    procesos = opt.procesos_pesados()     # top consumidores de RAM/CPU
    stats = opt.estadisticas_sistema()    # CPU/RAM/Disco en vivo
"""

import os
import sys
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


# ── Modelo de una categoría limpiable ──────────────────────────────────────────

class CategoriaLimpieza:
    def __init__(self, clave: str, nombre: str, icono: str, descripcion: str,
                 rutas: List[Path], es_papelera: bool = False):
        self.clave = clave
        self.nombre = nombre
        self.icono = icono
        self.descripcion = descripcion
        self.rutas = [r for r in rutas if r]
        self.es_papelera = es_papelera
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
        local = os.environ.get("LOCALAPPDATA", "")
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

            # 3) Caché de miniaturas del Explorador
            explorer_cache = Path(local) / "Microsoft" / "Windows" / "Explorer" if local else None
            if explorer_cache:
                cats.append(CategoriaLimpieza(
                    "miniaturas", "Caché de miniaturas", "▸",
                    "Miniaturas que Windows regenera solo.",
                    [explorer_cache],
                ))

            # 4) Cachés de navegadores comunes
            rutas_nav = []
            if local:
                rutas_nav += [
                    Path(local) / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                    Path(local) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                    Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Cache",
                ]
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                rutas_nav.append(Path(appdata) / "Mozilla" / "Firefox" / "Profiles")
            cats.append(CategoriaLimpieza(
                "cache_navegadores", "Caché de navegadores", "▸",
                "Datos temporales de Chrome, Edge, Brave y Firefox.",
                rutas_nav,
            ))

            # 5) Papelera de reciclaje
            cats.append(CategoriaLimpieza(
                "papelera", "Papelera de reciclaje", "▸",
                "Vacía la papelera de forma segura.",
                [], es_papelera=True,
            ))
        else:
            # Linux/macOS: cachés del usuario
            home = Path.home()
            cats.append(CategoriaLimpieza(
                "cache_usuario", "Caché del usuario", "▸",
                "Caché en ~/.cache.",
                [home / ".cache"],
            ))

        return cats

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
                    t, c = self._tamano_dir(ruta)
                    total += t
                    n += c
                cat.tamano, cat.archivos = total, n
        return self.categorias

    def _tamano_dir(self, ruta: Path) -> tuple:
        total, n = 0, 0
        if not ruta or not ruta.exists():
            return 0, 0
        for raiz, _dirs, archivos in os.walk(ruta):
            for nombre in archivos:
                try:
                    fp = os.path.join(raiz, nombre)
                    total += os.path.getsize(fp)
                    n += 1
                except (OSError, PermissionError):
                    continue
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
        Devuelve {'liberado': bytes, 'archivos': n, 'detalle': [...], 'errores': n}.
        """
        liberado_total, archivos_total, errores = 0, 0, 0
        detalle = []

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

            for ruta in cat.rutas:
                liberado, n, err = self._limpiar_dir(ruta)
                liberado_total += liberado
                archivos_total += n
                errores += err
            detalle.append(
                f"{cat.icono} {cat.nombre}: {formatear_bytes(cat.tamano)} liberados"
            )

        return {
            "liberado": liberado_total,
            "archivos": archivos_total,
            "detalle": detalle,
            "errores": errores,
        }

    def _limpiar_dir(self, ruta: Path) -> tuple:
        """Borra el CONTENIDO de un directorio temporal, no el directorio."""
        liberado, n, errores = 0, 0, 0
        if not ruta or not ruta.exists():
            return 0, 0, 0
        for entrada in ruta.iterdir():
            try:
                if entrada.is_file() or entrada.is_symlink():
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
        return liberado, n, errores

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

    def estadisticas_sistema(self) -> Dict:
        if not psutil:
            return {"disponible": False}
        try:
            mem = psutil.virtual_memory()
            disco = psutil.disk_usage(os.path.abspath(os.sep))
            return {
                "disponible": True,
                "cpu": psutil.cpu_percent(interval=0.2),
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
    print("== ESCANEO ==")
    for c in opt.escanear(lambda m: None):
        print(f"  {c.icono} {c.nombre}: {formatear_bytes(c.tamano)} ({c.archivos} archivos)")
    print("\n== TOP PROCESOS ==")
    for p in opt.procesos_pesados(5):
        print(f"  {p['nombre']} (PID {p['pid']}): {p['ram_str']}")
    print("\n== SISTEMA ==")
    print(" ", opt.estadisticas_sistema())
