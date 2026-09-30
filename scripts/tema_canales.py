"""
scripts/tema_canales.py — Pasa los colores literales de la paleta a canales del tema.

El tema de color (nucleo/tema.py + ui_web/tema.js) redefine los tokens de
tokens/colors.css y sus canales «--x-rgb». Un `rgba(0,229,255,.5)` escrito a
mano no se enteraría, así que se reescribe como

    rgb(var(--cyan-500-rgb, 0 229 255) / .5)

— el mismo color con el tema por defecto (el respaldo es el propio literal, y
colors.css define --cyan-500-rgb con esos números) y el color del tema cuando
luneTema lo redefine. Solo se tocan los rgb()/rgba() cuyos números son EXACTAMENTE
los de un token cian, azul, amarillo o tinta de colors.css; negros, blancos,
grises y rojos se quedan como están. El alfa se copia tal cual («.10» sigue
siendo «.10»).

Determinista e idempotente: lo convertido ya no coincide con el patrón, así que
una segunda pasada no cambia nada. Conserva la codificación UTF-8 y los finales
de línea de cada archivo.

Es la forma acordada de tocar ui_web/_ds_bundle.js (lo genera una herramienta
externa a partir de components/; no se edita a mano): sus rgba están en las
cadenas CSS de los componentes, igual que en los .jsx de origen.

Uso:
    python scripts/tema_canales.py                 # los archivos por defecto
    python scripts/tema_canales.py --comprobar     # solo dice si falta algo (sale con 1)
    python scripts/tema_canales.py ruta.css …      # otros archivos (p. ej. index.html)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
UI_WEB = RAIZ / "ui_web"
COLORES = UI_WEB / "tokens" / "colors.css"
FAMILIAS = ("cyan", "blue", "yellow", "ink")

_TOKEN_HEX = re.compile(r"--((?:%s)-\d+)\s*:\s*#([0-9A-Fa-f]{6})\b" % "|".join(FAMILIAS))
# rgb()/rgba() con comas: «rgba(0,229,255,.5)», «rgba( 0, 229, 255, 0.5 )», «rgb(0,229,255)».
_LITERAL = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9]*\.?[0-9]+%?)\s*)?\)")


def canales_de_colores(ruta: Path = COLORES) -> Dict[Tuple[int, int, int], str]:
    """(r, g, b) → nombre del token («cyan-500») de los tokens hex de colors.css."""
    css = ruta.read_text(encoding="utf-8")
    res: Dict[Tuple[int, int, int], str] = {}
    for nombre, h in _TOKEN_HEX.findall(css):
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        res.setdefault(rgb, nombre)            # el primero que aparece manda (determinista)
    return res


def convertir(texto: str, canales: Dict[Tuple[int, int, int], str]) -> Tuple[str, int]:
    """Texto con los literales de la paleta pasados a canales → (texto, cuántos)."""
    n = 0

    def cambio(m: re.Match) -> str:
        nonlocal n
        rgb = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        token = canales.get(rgb)
        if token is None:
            return m.group(0)
        n += 1
        respaldo = f"var(--{token}-rgb, {rgb[0]} {rgb[1]} {rgb[2]})"
        alfa = m.group(4)
        return f"rgb({respaldo} / {alfa})" if alfa is not None else f"rgb({respaldo})"

    return _LITERAL.sub(cambio, texto), n


def archivos_por_defecto(raiz: Path = RAIZ) -> List[Path]:
    """Los del tema (corte 4, agente C): tokens, componentes, páginas de la asistente
    y el bundle. index.html va aparte (se le puede pasar como argumento)."""
    ui = raiz / "ui_web"
    lista = [ui / "tokens" / "base.css", ui / "tokens" / "effects.css"]
    lista += sorted((ui / "components").rglob("*.jsx"))
    lista += [ui / "companion.html", ui / "companion_vrm.html", ui / "_ds_bundle.js"]
    return lista


def procesar(rutas: Iterable[Path], canales: Dict[Tuple[int, int, int], str], *,
             escribir: bool = True) -> Dict[Path, int]:
    """Convierte cada archivo (en sitio si `escribir`). → {ruta: literales convertidos}."""
    res: Dict[Path, int] = {}
    for ruta in rutas:
        with open(ruta, "r", encoding="utf-8", newline="") as f:     # conserva \r\n
            texto = f.read()
        nuevo, n = convertir(texto, canales)
        res[ruta] = n
        if n and escribir:
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                f.write(nuevo)
    return res


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("archivos", nargs="*", type=Path, help="archivos a convertir (por defecto, los del tema)")
    ap.add_argument("--comprobar", action="store_true", help="no escribe; sale con 1 si queda algo por convertir")
    args = ap.parse_args(argv)
    rutas = [p if p.is_absolute() else (Path.cwd() / p) for p in args.archivos] or archivos_por_defecto()
    canales = canales_de_colores()
    res = procesar(rutas, canales, escribir=not args.comprobar)
    total = sum(res.values())
    for ruta, n in res.items():
        if n:
            try:
                nombre = ruta.resolve().relative_to(RAIZ).as_posix()
            except ValueError:
                nombre = str(ruta)
            print(f"{'pendientes' if args.comprobar else 'convertidos'}: {n:3d}  {nombre}")
    if args.comprobar:
        print("todo en canales" if not total else f"faltan {total} literales por convertir")
        return 1 if total else 0
    print(f"{total} literales convertidos en {sum(1 for n in res.values() if n)} archivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
