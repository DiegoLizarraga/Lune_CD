"""
scripts/convertir_asistente.py — Convierte los videos de la asistente a WebM/VP9.

QtWebEngine (la piel web de Lune) NO reproduce H.264/MP4, pero SÍ VP9/WebM.
Por eso los videos de la asistente se sirven como .webm. Este script toma
cualquier `lune-<estado>.mp4` de la carpeta y lo convierte (y borra el .mp4).

Tamaño (11.2): los clips se ven a 240×430 en la asistente de escritorio y a unos
290×520 en la barra lateral, así que se guardan a 480×854 (el doble, para pantallas
al 150–200 %) y 24 fps. Decodificar un clip de 1080×1920 a 30 fps cuesta unas cinco
veces más y en la asistente (ventana translúcida) cada frame además pasa por Qt.
Sin canal alfa: los clips traen su fondo (yuv420p).

Uso:
    pip install imageio-ffmpeg      # trae un ffmpeg estático (solo para convertir)
    python scripts/convertir_asistente.py              # los .mp4 nuevos → .webm
    python scripts/convertir_asistente.py --reducir    # además, los .webm que pasen de
                                                       # 480 de ancho o de 24 fps, en su sitio

Nombres esperados (los que lee la UI), uno por emoción o estado:
    lune-composed · lune-happy · lune-sad · lune-angry · lune-surprised
    lune-thinking · lune-curious · lune-nervous · lune-wave · lune-dismiss
    lune-laughing · lune-bored · lune-listening · lune-talking · lune-working
Guarda el clip nuevo como `lune-<estado>.mp4` y corre este script. Los espacios
en el nombre se quitan solos (`lune-working .mp4` → `lune-working.webm`).
"""
import re
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "ui_web" / "assets" / "asistente" / "anime-videos"

ANCHO = 480           # alto proporcional (9:16 → 854)
FPS = 24
CRF = 32              # VP9 con calidad constante: a 480 px, 32 se ve igual que el 36 de antes a 720


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"   # se confía en el del PATH


def orden_vp9(ff: str, origen: Path, destino: Path) -> list:
    """La línea de ffmpeg: VP9 a ANCHO px (alto par y proporcional) y FPS, sin audio ni alfa."""
    return [ff, "-y", "-i", str(origen),
            "-vf", f"scale={ANCHO}:-2:flags=lanczos,fps={FPS},setsar=1",
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(CRF), "-row-mt", "1",
            "-cpu-used", "2", "-deadline", "good", "-an", "-pix_fmt", "yuv420p", str(destino)]


def medidas(ff: str, archivo: Path) -> tuple:
    """(ancho, alto, fps) del primer vídeo de `archivo` (ffmpeg -i); (0, 0, 0.0) si no se sabe."""
    r = subprocess.run([ff, "-hide_banner", "-i", str(archivo)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5}).*?(\d+(?:\.\d+)?) fps", r.stderr or "")
    if not m:
        return 0, 0, 0.0
    return int(m.group(1)), int(m.group(2)), float(m.group(3))


def hace_falta_reducir(ancho: int, fps: float) -> bool:
    return ancho > ANCHO or fps > FPS + 0.01


def convertir(ff: str, origen: Path, destino: Path) -> bool:
    r = subprocess.run(orden_vp9(ff, origen, destino), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode == 0 and destino.exists() and destino.stat().st_size > 0:
        return True
    print("   FALLÓ:\n" + (r.stderr or "")[-500:])
    return False


def reducir(ff: str) -> int:
    """Recodifica en su sitio los .webm más grandes que ANCHO o más rápidos que FPS."""
    hechos = 0
    for f in sorted(DIR.glob("lune-*.webm")):
        ancho, alto, fps = medidas(ff, f)
        if not ancho or not hace_falta_reducir(ancho, fps):
            continue
        tmp = f.with_name(f.stem + ".tmp.webm")
        antes = f.stat().st_size
        print(f"→ {f.name}: {ancho}×{alto} a {fps:g} fps")
        if convertir(ff, f, tmp):
            tmp.replace(f)
            hechos += 1
            print(f"   ok · {antes // 1024} KB → {f.stat().st_size // 1024} KB")
        else:
            tmp.unlink(missing_ok=True)
    return hechos


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ff = _ffmpeg()
    mp4s = sorted(DIR.glob("lune-*.mp4"))
    if not mp4s:
        print(f"No hay lune-*.mp4 que convertir en {DIR}")
    for f in mp4s:
        # Sin espacios ni mayúsculas: la UI busca exactamente `lune-<estado>.webm`.
        webm = f.with_name(f.stem.replace(" ", "").lower() + ".webm")
        print(f"→ {f.name} → {webm.name}")
        if convertir(ff, f, webm):
            f.unlink(missing_ok=True)
            print(f"   ok · {webm.stat().st_size // 1024} KB")
    if "--reducir" in argv:
        print(f"{reducir(ff)} clips reducidos a {ANCHO} px y {FPS} fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
