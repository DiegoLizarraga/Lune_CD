"""
Anticheat: Lune no usa nada que un antitrampas de juegos marque como sospechoso.

Mate-Engine se anuncia «Anti Cheat Safe» porque no engancha el teclado ni el
ratón del sistema ni toca la memoria de otros procesos. Lune sigue la misma
regla (ver el plan de la serie 10.3, principio 4):

- nada de hooks globales de teclado/ratón (ni `keyboard` ni `pynput`, ni
  SetWindowsHookEx): los atajos van con RegisterHotKey y la entrada global se
  lee sondeando (GetLastInputInfo, GetAsyncKeyState solo del clic izquierdo);
- nada de escribir en la memoria de otro proceso ni de crear hilos en él
  (WriteProcessMemory, CreateRemoteThread);
- nada de ganchos de eventos de ventanas del sistema (la función «SetWin» +
  «EventHook» de user32): sentarse en ventanas (corte 7) sondea con
  EnumWindows/GetWindowRect solo mientras hace falta, sin enganchar nada.

Este test recorre el código del repo (.py, .js, .mjs, .jsx) y falla si aparece
cualquiera de esas cadenas, aunque sea en un comentario: así nadie las mete sin
darse cuenta. Quedan fuera tests/ (que las nombra para comprobarlas), el código
de terceros (ui_web/vendor, node_modules) y las carpetas de entornos y cachés.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

EXTENSIONES = {".py", ".js", ".mjs", ".jsx"}

# Carpetas (relativas a la raíz) que no se miran.
EXCLUIDAS_RUTA = {
    ("tests",),
    ("ui_web", "vendor"),
    ("telegram-bot-or", "node_modules"),
}
# Nombres de carpeta que no se miran estén donde estén.
EXCLUIDAS_NOMBRE = {"node_modules", "__pycache__", ".git", ".venv", "venv", "env", "ENV",
                    ".pytest_cache", ".ruff_cache", "build", "dist"}

# Las cadenas se construyen por partes: este archivo no debe contenerlas literales
# (por si alguien quita tests/ de la exclusión).
PROHIBIDAS = [
    "import " + "keyboard",
    "from " + "keyboard",
    "pyn" + "put",
    "SetWindows" + "HookEx",
    "WriteProcess" + "Memory",
    "CreateRemote" + "Thread",
    "SetWin" + "EventHook",
]


def _excluida(partes: tuple) -> bool:
    """¿Se salta la carpeta con estas partes de ruta relativa?"""
    if partes and partes[-1] in EXCLUIDAS_NOMBRE:
        return True
    return any(partes[:len(pref)] == pref for pref in EXCLUIDAS_RUTA)


def _archivos():
    # os.walk podando: no se entra en node_modules (pueden ser decenas de miles de archivos).
    for carpeta, subcarpetas, nombres in os.walk(RAIZ):
        base = Path(carpeta).relative_to(RAIZ).parts
        subcarpetas[:] = [s for s in subcarpetas if not _excluida(base + (s,))]
        for nombre in nombres:
            if Path(nombre).suffix.lower() in EXTENSIONES:
                ruta = Path(carpeta) / nombre
                yield ruta, ruta.relative_to(RAIZ)


def test_se_recorre_el_codigo_de_verdad():
    """Que la exclusión no deje el test vacío (daría un verde falso)."""
    vistos = {rel.as_posix() for _, rel in _archivos()}
    for esperado in ("main.py", "patata.py", "nucleo/config.py", "servicios/atajos_globales.py",
                     "servicios/win_entrada.py", "ui/companion.py", "ui_web/vrm/lune_vrm.js",
                     "ui_web/lune_eventos.js", "servicios/ventanas_ajenas.py", "ui/asiento_qt.py",
                     "nucleo/asiento.py", "servicios/win_ventana.py"):
        assert esperado in vistos, esperado
    assert not any(v.startswith(("tests/", "ui_web/vendor/")) for v in vistos)


def test_sin_hooks_globales_ni_inyeccion_en_otros_procesos():
    encontrados = []
    for ruta, rel in _archivos():
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, linea in enumerate(texto.splitlines(), 1):
            for cadena in PROHIBIDAS:
                if cadena in linea:
                    encontrados.append(f"{rel.as_posix()}:{n}: {cadena!r} → {linea.strip()[:120]}")
    assert not encontrados, "Código que un antitrampas marcaría:\n" + "\n".join(encontrados)


def test_prohibe_los_ganchos_de_eventos_de_ventanas():
    """Corte 7: sentarse en ventanas sondea; el gancho de eventos de ventanas queda vetado."""
    cadena = "SetWin" + "EventHook"
    assert cadena in PROHIBIDAS
    linea = "u." + cadena + "(0x800B, 0x800B, None, cb, 0, 0, 0)"
    assert [c for c in PROHIBIDAS if c in linea] == [cadena]
