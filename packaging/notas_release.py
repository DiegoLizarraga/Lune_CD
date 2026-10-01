"""
packaging/notas_release.py — Las notas del Release de GitHub, en español.

    python packaging/notas_release.py 11.2                 (a la salida estándar)
    python packaging/notas_release.py 11.2 -o notas.md     (a un archivo, en UTF-8)
    python packaging/notas_release.py 11.2 --sha256 <hash | archivo .sha256>

Lo que dice:
  · la fila de esa versión en «Historial de versiones» del README (la misma que escribes al
    cerrar cada versión); si todavía no hay, un texto genérico;
  · cómo instalar (el Setup.exe, el aviso de SmartScreen porque no está firmado, y dónde
    encontrarme en el menú Inicio);
  · dónde quedan tus datos;
  · el SHA-256 del instalador (si no se lo das, lo busca en dist/LuneCD-Setup-<v>.exe.sha256).

Lo usa .github/workflows/release.yml con --notes-file.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

RAIZ = Path(__file__).resolve().parent.parent
TITULO_HISTORIAL = "## Historial de versiones"
_RE_FILA = re.compile(r"^\|\s*(?:\*\*)?v?(?P<version>[^|*\s]+)(?:\*\*)?\s*\|\s*(?P<texto>.*?)\s*\|\s*$")
_RE_HASH = re.compile(r"^[0-9a-fA-F]{64}$")


def nombre_setup(version: str) -> str:
    return f"LuneCD-Setup-{version}.exe"


def fila_historial(readme: str, version: str) -> Optional[str]:
    """El texto de la fila de `version` en la tabla del historial del README (None si no hay)."""
    dentro = False
    for linea in readme.splitlines():
        if linea.startswith("## "):
            dentro = linea.strip() == TITULO_HISTORIAL
            continue
        if not dentro:
            continue
        m = _RE_FILA.match(linea.strip())
        if m and m.group("version") == version:
            return m.group("texto").strip() or None
    return None


def leer_sha256(valor: Optional[str], version: str, raiz: Path = RAIZ) -> Optional[str]:
    """El hash: tal cual si es uno, o la primera palabra del archivo .sha256 indicado (o del de dist/)."""
    if valor and _RE_HASH.match(valor.strip()):
        return valor.strip().lower()
    ruta = Path(valor) if valor else raiz / "dist" / (nombre_setup(version) + ".sha256")
    try:
        primero = ruta.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None
    return primero.lower() if _RE_HASH.match(primero) else None


def notas(version: str, readme: str, sha: Optional[str] = None) -> str:
    setup = nombre_setup(version)
    cambios = fila_historial(readme, version) or (
        "Una versión nueva de Lune. Los detalles están en el «Historial de versiones» del README.")
    if sha:
        verificacion = (f"```\n{sha}  {setup}\n```\n\n"
                        f"En PowerShell, `(Get-FileHash .\\{setup} -Algorithm SHA256).Hash` tiene que dar lo "
                        f"mismo (sin importar mayúsculas). También va en `{setup}.sha256`, aquí abajo.")
    else:
        verificacion = (f"Está en `{setup}.sha256`, aquí abajo. En PowerShell, "
                        f"`(Get-FileHash .\\{setup} -Algorithm SHA256).Hash` tiene que dar lo mismo.")
    return f"""## Lune CD {version}

{cambios}

### Cómo instalarme

1. Descarga **{setup}** (aquí abajo, en *Assets*).
2. Ábrelo. Como el instalador no está firmado, Windows puede avisarte con «Windows protegió su PC» (SmartScreen): pulsa **Más información** y luego **Ejecutar de todas formas**.
3. Me instalo solo para ti, sin pedir permisos de administrador, en `%LOCALAPPDATA%\\Programs\\Lune CD`.
4. Búscame en el menú Inicio como **Lune** («Lune CD», y «Lune CD (terminal)» si me prefieres en la consola).

Si ya me tenías instalada, este mismo instalador me actualiza y tus cosas se quedan como estaban. Necesito Windows 10 u 11 de 64 bits.

### Dónde quedan tus cosas

- **Tus datos** (ajustes, chats, lo que recuerdo de ti, notas, alarmas, bailes, modelos VRM y tus API keys): `%APPDATA%\\Lune CD`. Ni el instalador ni las actualizaciones los tocan; si me desinstalas, te pregunto si los borro (por defecto, no).
- **Lo pesado o desechable** (registros, cachés y los bots de Telegram y Minecraft): `%LOCALAPPDATA%\\Lune CD`.
- Si me usas desde el código (git), esa copia sigue igual que siempre, con sus datos en la carpeta del repo.

### Comprobar la descarga (SHA-256)

{verificacion}
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Notas del Release de GitHub para una versión de Lune.")
    p.add_argument("version", help="la versión (la de version.py), p. ej. 11.2")
    p.add_argument("--sha256", help="el hash o la ruta del .sha256 (por defecto, el de dist/)")
    p.add_argument("--readme", default=str(RAIZ / "README.md"), help="README con el historial")
    p.add_argument("-o", "--salida", help="archivo donde escribirlas (UTF-8); sin esto, a la pantalla")
    args = p.parse_args(argv)
    try:
        readme = Path(args.readme).read_text(encoding="utf-8")
    except OSError:
        readme = ""
    texto = notas(args.version, readme, leer_sha256(args.sha256, args.version))
    if args.salida:
        Path(args.salida).write_text(texto, encoding="utf-8")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
