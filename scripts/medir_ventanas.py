"""
scripts/medir_ventanas.py — Cuánto cuesta el sondeo de «sentarse en ventanas».

Mide, con las ventanas REALES del escritorio y SOLO LEYENDO (no mueve ni
reordena nada, ni siquiera ventanas propias):

1. `listar_candidatas` (la enumeración que corre a 15 Hz mientras arrastras a
   la asistente con «Sentarse en ventanas» activo), N veces.
2. `barra_asiento` (lo que corre a 4 Hz con solo la barra), N veces.
3. El tic de «sentada» (15 Hz, 60 Hz en ráfagas) sobre la ventana activa o la
   primera candidata: `estado_ventana` + `rect_visible` + `monitor` +
   `encima_de` (la parte de lectura; el SetWindowPos de la ventana propia no se
   hace aquí).
4. `ocluida_en` en el centro del borde superior de esa ventana (solo al encajar).

Uso:  python scripts/medir_ventanas.py [N=100]
Salida: media, mediana, p95 y máximo en ms, y el recuento de ventanas.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import ventanas_ajenas as va  # noqa: E402
from servicios import win_pantalla as wp  # noqa: E402


def _consciente_de_dpi() -> None:
    """Como Qt 6: consciente de DPI por monitor (v2), para medir en px físicos."""
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


def _medir(nombre: str, fn, n: int) -> list:
    fn()                                             # calentamiento (firmas, cachés)
    tiempos = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        tiempos.append((time.perf_counter() - t0) * 1000.0)
    tiempos.sort()
    p95 = tiempos[min(len(tiempos) - 1, int(round(0.95 * (len(tiempos) - 1))))]
    print(f"{nombre:<34} media {statistics.fmean(tiempos):7.3f} ms · mediana {statistics.median(tiempos):7.3f}"
          f" · p95 {p95:7.3f} · máx {tiempos[-1]:7.3f}   (n={n})")
    return tiempos


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    n = int(argv[0]) if argv else 100
    if sys.platform != "win32":
        print("Solo en Windows.")
        return 0
    _consciente_de_dpi()
    api = va.api_defecto()
    pantalla = wp.api_defecto()
    pid = os.getpid()

    todas = api.enumerar()
    visibles = [h for h in todas if api.visible(h)]
    cands = va.listar_candidatas(api, excluir_pid=pid)
    print(f"Ventanas de primer nivel: {len(todas)} · visibles: {len(visibles)} · candidatas: {len(cands)}"
          f" ({sum(1 for c in cands if c.es_barra)} barras)")
    for c in cands[:12]:
        print(f"  {'BARRA ' if c.es_barra else 'ventana'} hwnd={c.hwnd:#x} rect={tuple(c.rect)}"
              f"{' topmost' if c.topmost else ''} clase={api.clase(c.hwnd)!r}")
    print()

    _medir("enumerar (EnumWindows)", api.enumerar, n)
    _medir("listar_candidatas (15 Hz)", lambda: va.listar_candidatas(api, excluir_pid=pid), n)
    _medir("listar_candidatas solo ventanas", lambda: va.listar_candidatas(api, excluir_pid=pid, barras=False), n)

    mons = wp.monitores(pantalla)
    if mons:
        r = mons[0].rect
        _medir("barra_asiento (4 Hz)", lambda: va.barra_asiento(r, pantalla), n)
        print(f"  barra del monitor 1: {va.barra_asiento(r, pantalla)}")

    objetivo = api.activa()
    if not objetivo or va.estado_ventana(api, objetivo) != "ok":
        objetivo = next((c.hwnd for c in cands if not c.es_barra), 0)
    if objetivo:
        otra = next((c.hwnd for c in cands if c.hwnd != objetivo), objetivo)

        def tic():
            va.estado_ventana(api, objetivo)
            api.rect_visible(objetivo)
            api.monitor(objetivo)
            va.encima_de(api, otra, objetivo, pasos=64)

        _medir("tic sentada (lectura)", tic, n)
        rv = api.rect_visible(objetivo)
        if rv:
            cx, cy = (rv.izq + rv.der) // 2, rv.arriba + 2
            _medir("ocluida_en (al encajar)", lambda: va.ocluida_en(api, objetivo, cx, cy, excluir_pid=pid), n)
            print(f"  objetivo hwnd={objetivo:#x} estado={va.estado_ventana(api, objetivo)} rect_visible={tuple(rv)}"
                  f" GetWindowRect={tuple(api.rect(objetivo) or ())}")
    else:
        print("Sin ventana objetivo para medir el tic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
