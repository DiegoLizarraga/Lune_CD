"""
packaging/construir.py — Construye Lune instalable: la carpeta con los .exe y el Setup.exe.

    python packaging/construir.py                 todo (con el Python del venv de build)
    python packaging/construir.py --sin-instalador   sin Inno Setup (solo dist/Lune CD)
    python packaging/construir.py --iscc RUTA     el ISCC.exe de Inno Setup a usar
    python packaging/construir.py --python RUTA   el Python con PyInstaller (por defecto, este)

Pasos (cada uno para el build si falla):
  1. Copia a build/fuente/ SOLO lo que va en el paquete, a partir de
     «git ls-files -co --exclude-standard»: lo que git ignora (datos.json con tus API keys,
     config.json, memoria.json, chats/, node_modules/…) no puede colarse. Encima hay una
     lista de lo que NUNCA entra, por si algún día falla el .gitignore.
  2. node packaging/compilar_web.mjs build/fuente/ui_web: los .jsx ya traducidos, sin Babel
     ni React de desarrollo (solo en la copia; el repo no se toca).
  3. PyInstaller con packaging/lune.spec → dist/Lune CD/ (Lune.exe, LunePatata.exe, _internal/).
     Luego comprueba que quedó UNA sola msvcp140.dll, y nueva (el crash del dictado).
  4. Prueba de humo: «dist/Lune CD/LunePatata.exe --comprobar» con LUNE_CD_DATOS en una
     carpeta temporal (nunca tus datos). Si no sale 0, no hay instalador.
  5. Inno Setup (packaging/lune.iss) → dist/LuneCD-Setup-<versión>.exe
  6. dist/LuneCD-Setup-<versión>.exe.sha256 («<hash>  <nombre>», como sha256sum).

La versión sale de version.py. En GitHub lo corre .github/workflows/release.yml.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

RAIZ = Path(__file__).resolve().parent.parent
AQUI = RAIZ / "packaging"
SPEC = AQUI / "lune.spec"
ISS = AQUI / "lune.iss"
NOMBRE_CARPETA = "Lune CD"
EXE_PATATA = "LunePatata.exe"
EXE_APP = "Lune.exe"
MSVC_MINIMA = (14, 40)
RUNTIME_CPP = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll")

# ── Qué entra en el paquete (rutas del repo, con «/») ─────────────────────────────
ARCHIVOS_RAIZ = frozenset({"main.py", "patata.py", "version.py", "datos.example.json"})
PAQUETES = ("nucleo/", "servicios/", "ui/", "lune_core/")
CARPETAS = ("assets/", "fonts/", "lune_face/", "sonidos/default/", "ui_web/")

# lune_core: solo sirven para «python -m lune_core serve|token», que no se alcanza desde
# main.py ni patata.py. Entran solos si algo del paquete los importa (alcanzados()).
LUNE_CORE_APARTE = {
    "lune_core/__main__.py": "lune_core.__main__",
    "lune_core/web_server.py": "lune_core.web_server",
    "lune_core/servicio_chat.py": "lune_core.servicio_chat",
}
LUNE_CORE_WEB = "lune_core/web/"            # la página de web_server.py

# De ui_web/ sobra lo del sistema de diseño (components/ ya va compilado en _ds_bundle.js).
UI_WEB_FUERA_CARPETAS = ("components/", "guidelines/")
UI_WEB_FUERA_ARCHIVOS = frozenset({"skill.md", "readme.md", "_ds_manifest.json", "thumbnail.html", ".thumbnail"})

# Los bots de Node: el código y su lockfile; nunca node_modules/ ni data/ (memoria de usuarios).
MINECRAFT = frozenset({"minecraft-bot/package.json", "minecraft-bot/package-lock.json", "minecraft-bot/LEEME.md"})
TELEGRAM = frozenset({"telegram-bot-or/package.json", "telegram-bot-or/package-lock.json"})

# Lo que NUNCA entra, aunque git lo listara (tus datos y las API keys).
NUNCA_NOMBRES = frozenset({"datos.json", "config.json", "memoria.json", "alarmas.json", "api_keys.json",
                           ".env", ".env.local", "instalacion.log"})
NUNCA_PARTES = frozenset({"node_modules", "__pycache__", ".git", ".pytest_cache"})
NUNCA_CARPETAS_RAIZ = frozenset({"chats", "bailes", "notas", "modelo_vrm", "logs", "cache", "documents",
                                 "downloads", "modelos_voz", "build", "dist", "venv", ".venv", "tests"})


def _normal(ruta: str) -> str:
    r = str(ruta).replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def prohibido(ruta: str) -> bool:
    """True si `ruta` es algo tuyo o que no debe empaquetarse nunca."""
    r = _normal(ruta)
    partes = r.split("/")
    if partes[-1].lower() in NUNCA_NOMBRES or partes[-1].lower().endswith((".pyc", ".pyo")):
        return True
    if any(p in NUNCA_PARTES for p in partes):
        return True
    if partes[0] in NUNCA_CARPETAS_RAIZ:
        return True
    if r.startswith("telegram-bot-or/data/"):
        return True
    return False


def va_en_el_paquete(ruta: str) -> bool:
    """¿Esta ruta del repo entra en build/fuente? (sin mirar lune_core aparte: ver alcanzados)."""
    r = _normal(ruta)
    if not r or prohibido(r):
        return False
    if r in ARCHIVOS_RAIZ:
        return True
    if r.startswith(PAQUETES):
        if r in LUNE_CORE_APARTE or r.startswith(LUNE_CORE_WEB):
            return False
        return True
    if r.startswith("ui_web/"):
        resto = r[len("ui_web/"):]
        if resto.startswith(UI_WEB_FUERA_CARPETAS):
            return False
        if "/" not in resto and (resto.lower() in UI_WEB_FUERA_ARCHIVOS or resto.startswith("_adherence")):
            return False
        return True
    if r.startswith(CARPETAS):
        return True
    if r.startswith("minecraft-bot/"):
        return r in MINECRAFT or r.startswith("minecraft-bot/src/")
    if r.startswith("telegram-bot-or/"):
        resto = r[len("telegram-bot-or/"):]
        return r in TELEGRAM or ("/" not in resto and resto.endswith(".js"))
    return False


def seleccionar(rutas: Iterable[str]) -> List[str]:
    """De la lista de git, lo que va en el paquete (ordenado y sin repetir)."""
    return sorted({_normal(r) for r in rutas if va_en_el_paquete(r)})


def _importa(texto: str, relativo_a: str) -> Set[str]:
    """Módulos que importa un .py (nombres completos; los relativos, resueltos)."""
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return set()
    paquete = relativo_a.rsplit("/", 1)[0].replace("/", ".") if "/" in relativo_a else ""
    vistos: Set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            vistos.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if nodo.level:
                partes = paquete.split(".") if paquete else []
                partes = partes[: len(partes) - (nodo.level - 1)] if nodo.level > 1 else partes
                base = ".".join([*partes, base] if base else partes)
            vistos.add(base)
            vistos.update(f"{base}.{a.name}" for a in nodo.names)
    # import_module("lune_core.web_server") y compañía
    vistos.update(re.findall(r"""["']((?:lune_core)\.[A-Za-z_][\w.]*)["']""", texto))
    return vistos


def alcanzados(raiz: Path, elegidos: Sequence[str]) -> List[str]:
    """Los de LUNE_CORE_APARTE que algo del paquete importa (y lo que arrastran)."""
    por_modulo = {m: r for r, m in LUNE_CORE_APARTE.items()}
    extra: List[str] = []
    pendientes = [r for r in elegidos if r.endswith(".py")]
    while pendientes:
        ruta = pendientes.pop()
        try:
            texto = (raiz / ruta).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for modulo in _importa(texto, ruta):
            nueva = por_modulo.get(modulo)
            if nueva and nueva not in extra and (raiz / nueva).is_file():
                extra.append(nueva)
                pendientes.append(nueva)
    if "lune_core/web_server.py" in extra:
        web = raiz / LUNE_CORE_WEB
        if web.is_dir():
            extra += sorted(_normal(str(p.relative_to(raiz))) for p in web.rglob("*") if p.is_file())
    return extra


def listar_git(raiz: Path = RAIZ) -> List[str]:
    """Lo versionado y lo nuevo que git no ignora (-co --exclude-standard)."""
    salida = subprocess.run(["git", "-C", str(raiz), "ls-files", "-co", "--exclude-standard", "-z"],
                            capture_output=True, check=True).stdout
    return [p for p in salida.decode("utf-8", "replace").split("\0") if p]


def elegir(raiz: Path, rutas: Iterable[str]) -> List[str]:
    """Selección final: lo que va, lo que existe en disco y lo de lune_core que se alcance."""
    elegidos = [r for r in seleccionar(rutas) if (raiz / r).is_file()]
    return sorted(set(elegidos) | set(alcanzados(raiz, elegidos)))


def copiar(raiz: Path, destino: Path, rutas: Sequence[str]) -> int:
    """Copia `rutas` de `raiz` a `destino` (vaciándolo antes). Devuelve los bytes copiados."""
    if destino.exists():
        shutil.rmtree(destino)
    total = 0
    for r in rutas:
        if prohibido(r):                               # segunda red, por si alguien llama sin elegir()
            raise RuntimeError(f"{r} no puede ir en el paquete")
        origen = raiz / r
        final = destino / r
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, final)
        total += final.stat().st_size
    return total


def leer_version(raiz: Path = RAIZ) -> str:
    texto = (raiz / "version.py").read_text(encoding="utf-8")
    m = re.search(r"""^APP_VERSION\s*=\s*["']([^"']+)["']""", texto, re.M)
    if not m:
        raise RuntimeError("version.py no tiene APP_VERSION")
    return m.group(1)


def version_windows(version: str) -> str:
    """«11.2» → «11.2.0.0» (lo que pide VersionInfoVersion de Inno)."""
    numeros = [str(int(n)) for n in re.findall(r"\d+", version)][:4]
    return ".".join((numeros + ["0", "0", "0", "0"])[:4])


def nombre_setup(version: str) -> str:
    return f"LuneCD-Setup-{version}.exe"


def buscar_iscc(dada: Optional[str] = None) -> Optional[Path]:
    """ISCC.exe: el que me digas, el del PATH o el de Program Files (en GitHub, choco)."""
    if dada:
        return Path(dada) if Path(dada).is_file() else None
    for nombre in ("iscc", "ISCC"):
        encontrado = shutil.which(nombre)
        if encontrado:
            return Path(encontrado)
    bases = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    for base in bases:
        if base:
            candidato = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidato.is_file():
                return candidato
    return None


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def escribir_sha256(ruta: Path) -> Path:
    destino = ruta.with_name(ruta.name + ".sha256")
    destino.write_text(f"{sha256(ruta)}  {ruta.name}\n", encoding="ascii", newline="\n")
    return destino


def tamano(ruta: Path) -> int:
    if ruta.is_file():
        return ruta.stat().st_size
    return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file())


def mb(n: int) -> str:
    return f"{n / (1024 * 1024):,.1f} MB".replace(",", ".")


def revisar_runtime(carpeta: Path) -> str:
    """El runtime de C++ del paquete: UNA copia de cada DLL (msvcp140, _1, _2, vcruntime140
    y _1), en la raíz de _internal, y la msvcp140.dll nueva (≥ 14.40). Si no, o el dictado
    cerraría Lune (nucleo/runtime_win.py) o, sin msvcp140_1/_2, Qt no arrancaría en un
    Windows sin el Visual C++ Redistributable. Devuelve un texto para el registro."""
    todos = [p for p in carpeta.rglob("*") if p.is_file()]
    raiz = carpeta / "_internal"
    for nombre in RUNTIME_CPP:
        copias = [p for p in todos if p.name.lower() == nombre]
        if len(copias) != 1 or copias[0].parent != raiz:
            lista = ", ".join(str(p.relative_to(carpeta)) for p in copias) or "ninguna"
            raise RuntimeError(f"tiene que haber UNA {nombre} en _internal y hay {len(copias)}: {lista}")
    copias = [raiz / "msvcp140.dll"]
    qt_bin = raiz / "PyQt6" / "Qt6" / "bin"
    viejas = [p.name for p in qt_bin.glob("*.dll")
              if re.match(r"^(msvcp140.*|vcruntime140.*|concrt140)\.dll$", p.name, re.I)] if qt_bin.is_dir() else []
    if viejas:
        raise RuntimeError(f"siguen en PyQt6/Qt6/bin: {', '.join(viejas)}")
    version = (0, 0, 0, 0)
    if sys.platform == "win32":
        sys.path.insert(0, str(RAIZ))
        from nucleo.runtime_win import version_dll
        version = version_dll(str(copias[0]))
        if version[:2] < MSVC_MINIMA:
            raise RuntimeError(f"la msvcp140.dll del paquete es vieja ({'.'.join(map(str, version))})")
    return f"{copias[0].relative_to(carpeta)} {'.'.join(map(str, version))}"


def entorno_limpio(**extra: str) -> dict:
    """El entorno para lanzar el exe congelado: sin PYTHONPATH ni PYTHONHOME de este Python."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(extra)
    return env


def _paso(titulo: str) -> float:
    print(f"\n== {titulo}", flush=True)
    return time.perf_counter()


def _correr(orden: Sequence[str], **kw) -> None:
    r = subprocess.run([str(o) for o in orden], **kw)
    if r.returncode != 0:
        raise RuntimeError(f"falló ({r.returncode}): {' '.join(str(o) for o in orden)}")


def construir(args: argparse.Namespace) -> int:
    inicio = time.perf_counter()
    tiempos = {}
    version = leer_version()
    build = RAIZ / "build"
    fuente = build / "fuente"
    dist = RAIZ / "dist"
    carpeta = dist / NOMBRE_CARPETA
    print(f"Lune CD {version}: construyendo desde {RAIZ}", flush=True)

    iscc = None
    if not args.sin_instalador:
        iscc = buscar_iscc(args.iscc)
        if iscc is None:
            raise RuntimeError("no encuentro ISCC.exe de Inno Setup (instálalo, pásalo con --iscc o usa "
                               "--sin-instalador)")

    t = _paso("1/6 Copia limpia en build/fuente")
    rutas = elegir(RAIZ, listar_git(RAIZ))
    copiado = copiar(RAIZ, fuente, rutas)
    print(f"{len(rutas)} archivos, {mb(copiado)}")
    tiempos["copia"] = time.perf_counter() - t

    t = _paso("2/6 Piel web precompilada (node packaging/compilar_web.mjs)")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("no encuentro node en el PATH (hace falta para precompilar la piel web)")
    _correr([node, str(AQUI / "compilar_web.mjs"), str(fuente / "ui_web")])
    tiempos["web"] = time.perf_counter() - t

    t = _paso("3/6 PyInstaller (packaging/lune.spec)")
    build.mkdir(exist_ok=True)
    _correr([args.python, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean",
             "--distpath", str(dist), "--workpath", str(build / "pyinstaller")],
            cwd=str(build), env=dict(os.environ, LUNE_FUENTE=str(fuente)))
    for exe in (EXE_APP, EXE_PATATA):
        if not (carpeta / exe).is_file():
            raise RuntimeError(f"PyInstaller no dejó {carpeta / exe}")
    print("runtime de C++:", revisar_runtime(carpeta))
    tiempos["pyinstaller"] = time.perf_counter() - t

    t = _paso("4/6 Prueba de humo: LunePatata.exe --comprobar")
    datos = Path(tempfile.mkdtemp(prefix="lune_comprobar_"))
    try:
        _correr([carpeta / EXE_PATATA, "--comprobar"], cwd=str(datos),
                env=entorno_limpio(LUNE_CD_DATOS=str(datos), PYTHONIOENCODING="utf-8"), timeout=600)
    finally:
        shutil.rmtree(datos, ignore_errors=True)
    tiempos["comprobar"] = time.perf_counter() - t

    setup = dist / nombre_setup(version)
    if iscc is not None:
        t = _paso(f"5/6 Instalador (Inno Setup: {iscc})")
        for viejo in (setup, setup.with_name(setup.name + ".sha256")):
            viejo.unlink(missing_ok=True)
        _correr([iscc, "/Q", f"/DVersion={version}", f"/DVersionWin={version_windows(version)}",
                 f"/DOrigen={carpeta}", f"/DSalida={dist}", str(ISS)])
        if not setup.is_file():
            raise RuntimeError(f"Inno Setup no dejó {setup}")
        tiempos["inno"] = time.perf_counter() - t

        _paso("6/6 SHA-256")
        print(escribir_sha256(setup).read_text(encoding="ascii").strip())

    total = time.perf_counter() - inicio
    print("\n== Listo")
    print(f"dist/{NOMBRE_CARPETA}: {mb(tamano(carpeta))}")
    if setup.is_file() and iscc is not None:
        print(f"dist/{setup.name}: {mb(tamano(setup))}")
    print("tiempos: " + ", ".join(f"{k} {v:.0f} s" for k, v in tiempos.items()) + f"; total {total:.0f} s")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Construye Lune instalable (PyInstaller + Inno Setup).")
    p.add_argument("--sin-instalador", action="store_true", help="solo dist/Lune CD, sin Inno Setup")
    p.add_argument("--iscc", help="ruta de ISCC.exe (por defecto: PATH y Program Files)")
    p.add_argument("--python", default=sys.executable, help="Python con PyInstaller (por defecto, este)")
    args = p.parse_args(argv)
    try:
        return construir(args)
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"\nNo se pudo construir: {e}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
