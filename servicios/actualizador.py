"""
actualizador.py — Traer cambios con git, instalar dependencias y reiniciar.

Pensado para el caso de tener Lune en varias máquinas: tocas algo en el PC de
casa, lo subes, y en la laptop pulsas «Actualizar» sin abrir una terminal.

SOBRE NO PISAR TU TRABAJO
-------------------------
`git pull` con cambios locales sin commitear puede acabar en conflicto o en
pérdida de trabajo. Por eso `actualizar()` se NIEGA a seguir si el árbol está
sucio y te dice exactamente qué archivos tienes tocados. Nada de --force,
--hard ni stash automático: si hay algo que decidir, lo decides tú.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

RAIZ = Path(__file__).parent.parent
TIMEOUT_GIT = 120

# En Windows, cada subprocess abre una ventana de consola que parpadea encima de
# la app. Con pythonw se ve especialmente feo: varias terminales asomando y
# robando el foco. CREATE_NO_WINDOW las ejecuta sin consola.
SIN_CONSOLA = {}
if os.name == "nt":
    SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


# ── Dependencias opcionales ────────────────────────────────────────────────────
# Único sitio donde se declara qué hace falta para cada función opcional.
# Lo usan el actualizador y el panel de ajustes para avisar al usuario.
OPCIONALES: Dict[str, Dict] = {
    "Voz de salida (Lune habla)": {
        "modulos": {"edge_tts": "edge-tts", "pygame": "pygame"},
        "nota": "Sin esto Lune no puede leer las respuestas en voz alta.",
    },
    "Voz de entrada (dictado)": {
        "modulos": {"faster_whisper": "faster-whisper", "sounddevice": "sounddevice"},
        "nota": "Transcripción local con Whisper. El audio no sale de tu equipo.",
    },
    "Leer PDF": {
        "modulos": {"pypdf": "pypdf"},
        "nota": "Para adjuntar documentos PDF al chat.",
    },
    "Leer Word (.docx)": {
        "modulos": {"docx": "python-docx"},
        "nota": "Para adjuntar documentos de Word al chat.",
    },
    "Optimizador del sistema": {
        "modulos": {"psutil": "psutil"},
        "nota": "Monitor de CPU/RAM y limpieza de archivos temporales. También lo usan el modo "
                "juego (bajar la prioridad de Lune), el recorte de RAM y el reconocer programas "
                "(música, Discord); sin él esas partes se saltan.",
    },
    "Interfaz completa (piel web animada)": {
        "modulos": {"PyQt6.QtWebEngineWidgets": "PyQt6-WebEngine"},
        "nota": "La interfaz Shibuya Punk / Nube con animaciones y la asistente en escritorio animada. "
                "Sin esto Lune usa la interfaz nativa ligera (modo bajos recursos).",
    },
    "Red local (descubrir dispositivos)": {
        "modulos": {"zeroconf": "zeroconf"},
        "nota": "Para que Lune encuentre otros equipos con Lune en tu red (host/terminales).",
    },
    "Comentar lo que ves en pantalla": {
        "modulos": {"PIL": "Pillow"},
        "nota": "La captura de pantalla con la que Lune comenta lo que tienes delante. "
                "Sin esto no puede mirar la pantalla (nunca lo hace con un juego abierto).",
    },
    "Voz 100% local (Kokoro)": {
        "modulos": {"kokoro_onnx": "kokoro-onnx"},
        "nota": "Lune habla sin internet. Además necesita espeak-ng y los pesos en modelos_voz/.",
    },
    "Voz de respaldo (gTTS)": {
        "modulos": {"gtts": "gtts"},
        "nota": "Si edge-tts falla, Lune habla con la voz de Google.",
    },
    "Conversión de voz RVC (experimental)": {
        "modulos": {"rvc_python": "rvc-python"},
        "nota": "Cambia el timbre de la voz con un modelo .pth. Muy pesado (arrastra torch).",
    },
}

# Lo que hace falta sí o sí (instalador para usuarios nuevos: va marcado por defecto).
# numpy es obligatorio: lo importan al cargar el mezclador de sonidos, el pulso de la
# música, «Mis bailes» (nucleo/bailes.py) y la canción de los bailes
# (servicios/cancion_python.py); sin él no hay sonidos de Lune, ni alarmas con
# sonido propio, ni bailes de la biblioteca.
NUCLEO: Dict[str, Dict] = {
    "Núcleo de Lune (obligatorio)": {
        "modulos": {"PyQt6": "PyQt6", "requests": "requests", "websockets": "websockets"},
        "nota": "La ventana, la conexión con los modelos y la red entre equipos. Sin esto no arranca.",
    },
    "Sonido: mezclador, alarmas y bailes (obligatorio)": {
        "modulos": {"numpy": "numpy", "sounddevice": "sounddevice", "imageio_ffmpeg": "imageio-ffmpeg"},
        "nota": "numpy: el mezclador de sonidos de Lune, las alarmas y los bailes (sin él no "
                "cargan) y el giro de los sprites. sounddevice: la salida del mezclador (sin él cae "
                "a winsound, sin mezcla). imageio-ffmpeg: un ffmpeg para leer mp3/ogg/m4a de "
                "alarmas y bailes (sin él solo .wav).",
    },
}
if sys.platform == "win32":
    NUCLEO["Windows: asistente en escritorio y detector de música (obligatorio)"] = {
        "modulos": {"win32gui": "pywin32", "comtypes": "comtypes"},
        "nota": "pywin32: el modo fantasma de la asistente en escritorio (deja pasar los clics y se "
                "queda sobre los juegos) "
                "y la ventana activa. comtypes: el detector de música y el audio por programa "
                "(bailar con lo que suena). Solo Windows.",
    }

# Lo que NO es de pip y avisa el instalador (los bots de Telegram y de Minecraft son Node).
NODE_MINIMO = 18
AVISO_NODE = (f"Node.js {NODE_MINIMO} o más nuevo (nodejs.org) para el bot de Telegram y el de "
              "Minecraft. El resto de Lune funciona sin él.")


def estado_node(which=None, ejecutar=None) -> Dict:
    """{ok, version, mensaje} de Node.js (requisito externo de los bots). No lanza."""
    import shutil
    which = which or shutil.which
    ejecutar = ejecutar or subprocess.run
    ruta = which("node")
    if not ruta:
        return {"ok": False, "version": "", "mensaje": f"Falta {AVISO_NODE}"}
    try:
        res = ejecutar([ruta, "--version"], capture_output=True, text=True, timeout=10, **SIN_CONSOLA)
        version = str(getattr(res, "stdout", "") or "").strip().splitlines()[0][:20]
    except Exception:
        version = ""
    try:
        mayor = int(version.lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        mayor = 0
    if mayor >= NODE_MINIMO:
        return {"ok": True, "version": version,
                "mensaje": f"Node.js {version}: OK (bots de Telegram y Minecraft)."}
    return {"ok": False, "version": version,
            "mensaje": f"Node.js {version or '(versión desconocida)'} es viejo: hace falta {AVISO_NODE}"}


def estado_opcionales() -> List[Dict]:
    """
    Qué funciones opcionales están listas y cuáles no; al final, las obligatorias
    (NUCLEO) a las que les falta algo (p. ej. numpy), para que Ajustes lo avise.
    [{funcion, disponible, faltan: [pip], comando, nota}]
    """
    resultado = []
    for funcion, info in [*OPCIONALES.items(), *NUCLEO.items()]:
        faltan = [
            paquete for modulo, paquete in info["modulos"].items()
            if importlib.util.find_spec(modulo) is None
        ]
        if not faltan and funcion in NUCLEO and funcion not in OPCIONALES:
            continue
        resultado.append({
            "funcion": funcion,
            "disponible": not faltan,
            "faltan": faltan,
            "comando": f"pip install {' '.join(faltan)}" if faltan else "",
            "nota": info["nota"],
        })
    return resultado


# ── Git ────────────────────────────────────────────────────────────────────────

def _git(*args, timeout: int = TIMEOUT_GIT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(RAIZ), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace", **SIN_CONSOLA,
    )


def hay_git() -> bool:
    try:
        return _git("--version", timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def es_repositorio() -> bool:
    if not (RAIZ / ".git").exists():
        return False
    try:
        return _git("rev-parse", "--is-inside-work-tree", timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def estado() -> Dict:
    """Rama, commit actual y si hay cambios sin guardar."""
    if not hay_git():
        return {"ok": False, "mensaje": "Git no está instalado o no está en el PATH."}
    if not es_repositorio():
        return {"ok": False,
                "mensaje": "Esta copia de Lune no es un repositorio git, así que no "
                           "puedo actualizarla sola. Clónala con git para usar esto."}
    rama = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    commit = _git("rev-parse", "--short", "HEAD").stdout.strip()
    sucio = _git("status", "--porcelain").stdout.strip()
    modificados = [l[3:].strip() for l in sucio.splitlines() if l.strip()] if sucio else []
    remoto = _git("remote", "get-url", "origin").stdout.strip()
    return {
        "ok": True, "rama": rama, "commit": commit, "remoto": remoto,
        "limpio": not modificados, "modificados": modificados,
    }


def comprobar(rama: Optional[str] = None) -> Dict:
    """
    Consulta el remoto sin tocar nada local (`git fetch`).
    Devuelve {ok, hay_novedades, pendientes, commits, mensaje}.
    """
    est = estado()
    if not est.get("ok"):
        return {"ok": False, "hay_novedades": False, "mensaje": est["mensaje"]}

    rama = rama or est["rama"]
    if not est.get("remoto"):
        return {"ok": False, "hay_novedades": False,
                "mensaje": "No hay un remoto «origin» configurado."}

    fetch = _git("fetch", "origin", rama)
    if fetch.returncode != 0:
        return {"ok": False, "hay_novedades": False,
                "mensaje": f"No pude consultar el remoto:\n{fetch.stderr.strip()[:300]}"}

    cuenta = _git("rev-list", "--count", f"HEAD..origin/{rama}").stdout.strip()
    try:
        pendientes = int(cuenta)
    except ValueError:
        pendientes = 0

    commits = []
    if pendientes:
        log = _git("log", "--oneline", "--no-decorate", f"HEAD..origin/{rama}")
        commits = [l.strip() for l in log.stdout.splitlines() if l.strip()]

    return {
        "ok": True,
        "hay_novedades": pendientes > 0,
        "pendientes": pendientes,
        "commits": commits,
        "rama": rama,
        "limpio": est["limpio"],
        "modificados": est["modificados"],
        "mensaje": (f"Hay {pendientes} cambio(s) nuevo(s) esperando."
                    if pendientes else "Ya estás en la última versión."),
    }


def actualizar(rama: Optional[str] = None, on_progreso=None) -> Dict:
    """
    Trae los cambios e instala dependencias.
    Devuelve {ok, actualizado, requisitos_ok, mensaje, detalle}.
    """
    def avisar(m):
        if on_progreso:
            on_progreso(m)

    est = estado()
    if not est.get("ok"):
        return {"ok": False, "actualizado": False, "mensaje": est["mensaje"]}

    rama = rama or est["rama"]

    # No tocamos nada si tienes trabajo sin guardar.
    if not est["limpio"]:
        listado = "\n".join(f"  · {a}" for a in est["modificados"][:12])
        extra = f"\n  … y {len(est['modificados']) - 12} más" if len(est["modificados"]) > 12 else ""
        return {
            "ok": False, "actualizado": False,
            "mensaje": ("Tienes cambios sin guardar y no quiero pisártelos.\n\n"
                        f"{listado}{extra}\n\n"
                        "Haz commit (o descarta) y vuelve a intentarlo."),
        }

    avisar("Trayendo cambios…")
    pull = _git("pull", "--ff-only", "origin", rama)
    if pull.returncode != 0:
        return {
            "ok": False, "actualizado": False,
            "mensaje": ("No pude actualizar sin rehacer historia. Suele pasar si "
                        "commiteaste algo aquí que no está en el remoto.\n\n"
                        f"{pull.stderr.strip()[:400]}"),
        }

    sin_cambios = "Already up to date" in pull.stdout or "Ya está actualizado" in pull.stdout
    detalle = pull.stdout.strip()

    # Dependencias
    avisar("Comprobando dependencias…")
    requisitos = RAIZ / "requirements.txt"
    requisitos_ok, salida_pip = True, ""
    if requisitos.exists():
        avisar("Instalando dependencias…")
        pip = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requisitos)],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace", **SIN_CONSOLA,
        )
        requisitos_ok = pip.returncode == 0
        salida_pip = (pip.stdout or "")[-500:] if requisitos_ok else (pip.stderr or "")[-500:]

    nuevo = estado()
    mensaje = ("Ya estabas en la última versión." if sin_cambios
               else f"Actualizado a {nuevo.get('commit', '?')}.")
    if not requisitos_ok:
        mensaje += "\n\nOJO: falló la instalación de dependencias, revisa el detalle."

    return {
        "ok": True,
        "actualizado": not sin_cambios,
        "requisitos_ok": requisitos_ok,
        "mensaje": mensaje,
        "detalle": (detalle + ("\n\n" + salida_pip if salida_pip else "")).strip(),
        "commit": nuevo.get("commit", ""),
    }


# ── Reinicio ───────────────────────────────────────────────────────────────────

def reiniciar():
    """
    Relanza la app con el mismo intérprete y argumentos.

    Se usa Popen + salida en vez de os.execv: en Windows, execv con Qt vivo deja
    la ventana colgada y el proceso zombi.
    """
    try:
        subprocess.Popen([sys.executable, *sys.argv], cwd=str(RAIZ),
                         close_fds=False, **SIN_CONSOLA)
    except Exception:
        return False
    os._exit(0)
