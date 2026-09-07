"""
scripts/convertir_mascota.py — Convierte los videos de la mascota a WebM/VP9.

QtWebEngine (la piel web de Lune) NO reproduce H.264/MP4, pero SÍ VP9/WebM.
Por eso los videos de la mascota se sirven como .webm. Este script toma
cualquier `lune-<estado>.mp4` de la carpeta y lo convierte (y borra el .mp4).

Uso:
    pip install imageio-ffmpeg      # trae un ffmpeg estático (solo para convertir)
    python scripts/convertir_mascota.py

Nombres esperados (los que lee la UI):
    lune-composed · lune-happy · lune-angry · lune-surprised · lune-wave
    lune-thinking · lune-nervous · lune-dismiss
Así que cuando agregues Nervous/Dismiss/Thinking, guárdalos como
`lune-nervous.mp4`, etc., y corre este script.
"""
import subprocess
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "ui_web" / "assets" / "mascot" / "anime-videos"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"   # se confía en el del PATH


def main() -> int:
    ff = _ffmpeg()
    mp4s = sorted(DIR.glob("lune-*.mp4"))
    if not mp4s:
        print(f"No hay lune-*.mp4 que convertir en {DIR}")
        return 0
    for f in mp4s:
        webm = f.with_suffix(".webm")
        print(f"→ {f.name} → {webm.name}")
        r = subprocess.run(
            [ff, "-y", "-i", str(f), "-c:v", "libvpx-vp9", "-b:v", "0",
             "-crf", "36", "-row-mt", "1", "-cpu-used", "5", "-deadline", "good",
             "-an", "-pix_fmt", "yuv420p", str(webm)],
            capture_output=True, text=True)
        if r.returncode == 0 and webm.exists():
            f.unlink(missing_ok=True)
            print(f"   ok · {webm.stat().st_size // 1024} KB")
        else:
            print("   FALLÓ:\n" + (r.stderr or "")[-500:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
