"""
servicios/copia_bots.py — Trae el código de los bots de Node (lo que trae Lune) a la
carpeta donde corren.

Instalada, el código de telegram-bot-or/ y minecraft-bot/ viene en _internal
(rutas.RECURSOS), que cada actualización reemplaza y donde no conviene dejar
node_modules. Los bots corren en otra carpeta:

  · Telegram en rutas.dato("telegram-bot-or"): así su «..» es DATOS, donde están
    datos.json, memoria.json y config.json, sin tocar el JS.
  · Minecraft en rutas.local("minecraft-bot"): sus ~400 MB de node_modules, fuera
    de la carpeta que viaja con el perfil (Roaming).

Antes de instalar o lanzar un bot se copia al destino lo que falte o haya cambiado de:
los *.js de la raíz del bot, package.json, package-lock.json y la carpeta src/ entera.
Nunca se tocan node_modules/, data/ (memorias y notas de voz del bot de Telegram) ni la
marca .instalando, y no se borra nada del destino. Cada archivo se escribe en un
temporal al lado y se cambia con os.replace: un bot que arranca a la vez nunca lee
medio archivo.

Desde el código origen y destino son la misma carpeta: no se copia nada.
"""
from __future__ import annotations

import filecmp
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import List, Union

_log = logging.getLogger("lune.copia_bots")

ARCHIVOS = frozenset({"package.json", "package-lock.json"})
CARPETAS = frozenset({"src"})
NUNCA = frozenset({"node_modules", "data", ".instalando"})

Ruta = Union[str, Path]


def misma_carpeta(a: Ruta, b: Ruta) -> bool:
    """¿Apuntan a la misma carpeta (aunque una no exista todavía)?"""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def archivos_del_bot(origen: Ruta) -> List[Path]:
    """Rutas RELATIVAS de lo que se copia de `origen` (vacía si no existe)."""
    origen = Path(origen)
    lista: List[Path] = []
    try:
        hijos = list(origen.iterdir())
    except OSError:
        return lista
    for hijo in hijos:
        if hijo.name in NUNCA:
            continue
        if hijo.is_file() and (hijo.suffix.lower() == ".js" or hijo.name in ARCHIVOS):
            lista.append(Path(hijo.name))
        elif hijo.is_dir() and hijo.name in CARPETAS:
            for f in hijo.rglob("*"):
                rel = f.relative_to(origen)
                if f.is_file() and not NUNCA.intersection(rel.parts):
                    lista.append(rel)
    return sorted(lista)


def _igual(a: Path, b: Path) -> bool:
    try:
        return b.is_file() and filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def sincronizar(origen: Ruta, destino: Ruta) -> bool:
    """Copia a `destino` los archivos del bot de `origen` que falten o hayan cambiado.

    True si el destino quedó al día (también si ya lo estaba, o si son la misma
    carpeta); False si no hay bot en `origen` o algún archivo no se pudo copiar (el
    bot sigue con lo que hubiera). Nunca lanza."""
    origen, destino = Path(origen), Path(destino)
    if misma_carpeta(origen, destino):
        return True
    lista = archivos_del_bot(origen)
    if not lista:
        _log.warning("copia_bots: no hay bot que copiar en %s", origen)
        return False
    ok, copiados = True, 0
    for rel in lista:
        src, dst = origen / rel, destino / rel
        if _igual(src, dst):
            continue
        tmp = dst.with_name(f".{dst.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            copiados += 1
        except OSError as e:
            ok = False
            _log.warning("copia_bots: no pude copiar %s a %s: %s", rel, destino, e)
            try:
                tmp.unlink()
            except OSError:
                pass
    if copiados:
        _log.info("copia_bots: %d archivo(s) del bot al día en %s", copiados, destino)
    return ok


__all__ = ("ARCHIVOS", "CARPETAS", "NUNCA", "misma_carpeta", "archivos_del_bot", "sincronizar")
