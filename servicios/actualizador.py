"""
actualizador.py — Ponerme al día: desde GitHub Releases (instalada) o con git (desde el código).

Tres modos (modo()):
  · "instalada": el Setup.exe de GitHub Releases (nucleo/rutas.INSTALADA). buscar_release()
    mira el último release de DiegoLizarraga/Lune_CD, descargar() baja su LuneCD-Setup-<v>.exe
    comprobando tamaño y SHA-256 y instalar() lo lanza en silencio (/RELANZAR=1: al acabar me
    vuelvo a abrir). Quien llama a instalar() cierra Lune de verdad (el «Salir» de la bandeja).
  · "git": la copia de desarrollo (hay .git). comprobar() hace `git fetch` y lista los commits;
    actualizar() hace `git pull --ff-only` y pip; reiniciar() me relanza.
  · "carpeta": una copia sin git (un ZIP). Solo aviso de que hay versión nueva con el enlace a
    la página de Releases; no toco nada.
buscar_novedades() despacha según el modo (el aviso al iniciar de las tres interfaces) y
toca_comprobar()/marcar_comprobacion() llevan la cuenta de «como mucho una vez al día».

Pensado también para tener Lune en varias máquinas: tocas algo en el PC de casa, lo subes, y
en la laptop pulsas «Actualizar» sin abrir una terminal.

SOBRE NO PISAR TU TRABAJO
-------------------------
`git pull` con cambios locales sin commitear puede acabar en conflicto o en
pérdida de trabajo. Por eso `actualizar()` se NIEGA a seguir si el árbol está
sucio y te dice exactamente qué archivos tienes tocados. Nada de --force,
--hard ni stash automático: si hay algo que decidir, lo decides tú.

SOBRE NO EJECUTAR NADA RARO
---------------------------
Solo se lanza un instalador que venga de github.com/DiegoLizarraga/Lune_CD (el asset del
release), descargado por HTTPS desde github.com o sus servidores de descargas (cada
redirección se valida antes de seguirla) y con su SHA-256 comprobado contra el que publica
GitHub (el campo "digest" del asset o el .sha256 que sube release.yml). Sin SHA-256 no se
descarga. Nada de tokens: sin ellos GitHub deja 60 consultas por hora, de sobra para una al día.
"""
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

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

    `comando` es nucleo/rutas.como_instalar: desde el código, la orden de pip;
    instalada, que eso no viene (todo lo que se puede ya va dentro). Instalada, las
    obligatorias no salen nunca: vienen con Lune y no hay pip con que arreglarlas.
    """
    from nucleo import rutas
    resultado = []
    for funcion, info in [*OPCIONALES.items(), *NUCLEO.items()]:
        es_nucleo = funcion in NUCLEO and funcion not in OPCIONALES
        if es_nucleo and rutas.INSTALADA:
            continue
        faltan = [
            paquete for modulo, paquete in info["modulos"].items()
            if importlib.util.find_spec(modulo) is None
        ]
        if not faltan and es_nucleo:
            continue
        resultado.append({
            "funcion": funcion,
            "disponible": not faltan,
            "faltan": faltan,
            "comando": rutas.como_instalar(*faltan) if faltan else "",
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

def orden_reinicio(pid: Optional[int] = None) -> List[str]:
    """La orden para relanzar este proceso (nucleo/rutas.orden_reinicio: desde el código
    [python, main.py, …]; instalada [Lune.exe, …]) con `--esperar-pid <este PID>`: la
    nueva espera a que esta muera antes de mirar la instancia única (si no, se conectaba
    a esta, que aún no se había ido, y se cerraba). Sin el --esperar-pid de antes."""
    from nucleo import arranque, rutas
    pid = os.getpid() if pid is None else int(pid)
    return [*arranque.sin_esperar_pid(rutas.orden_reinicio()), arranque.BANDERA_ESPERAR_PID, str(pid)]


def reiniciar(popen=None, salir=None):
    """
    Relanza la app con el mismo intérprete (o Lune.exe) y argumentos, y sale.

    Se usa Popen + salida en vez de os.execv: en Windows, execv con Qt vivo deja
    la ventana colgada y el proceso zombi. `popen` y `salir` son para los tests.
    """
    from nucleo import rutas
    try:
        (popen or subprocess.Popen)(orden_reinicio(), cwd=str(rutas.PROGRAMA),
                                    close_fds=False, **SIN_CONSOLA)
    except Exception:
        return False
    (salir or os._exit)(0)


# ── Modo: instalada, git o carpeta ─────────────────────────────────────────────

MODO_INSTALADA, MODO_GIT, MODO_CARPETA = "instalada", "git", "carpeta"


def modo(instalada: Optional[bool] = None, raiz: Optional[Path] = None) -> str:
    """"instalada" (el Setup.exe: nucleo/rutas.INSTALADA), "git" (una copia con .git) o
    "carpeta" (una copia sin git, p. ej. un ZIP: solo aviso con el enlace a Releases).
    `instalada` y `raiz` son para los tests."""
    if instalada is None:
        from nucleo import rutas
        instalada = rutas.INSTALADA
    if instalada:
        return MODO_INSTALADA
    raiz = Path(raiz) if raiz is not None else RAIZ
    return MODO_GIT if (raiz / ".git").exists() else MODO_CARPETA


def version_actual() -> str:
    """version.APP_VERSION (la única fuente de la versión)."""
    try:
        from version import APP_VERSION
        return str(APP_VERSION)
    except Exception:
        return ""


def version_tupla(texto: Any) -> Tuple[int, ...]:
    """«v11.2» → (11, 2); «11.2.1» → (11, 2, 1); lo que no empiece por un número → ()."""
    s = str(texto or "").strip().lstrip("vV").strip()
    m = re.match(r"(\d+(?:\.\d+)*)", s)
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split("."))


def _comparable(t: Tuple[int, ...]) -> Tuple[int, ...]:
    """(11, 2, 0) y (11, 2) son la misma versión: sin los ceros del final."""
    t = tuple(t)
    while t and t[-1] == 0:
        t = t[:-1]
    return t


def es_mas_nueva(nueva: Any, actual: Any) -> bool:
    """¿`nueva` es posterior a `actual`? Con una de las dos ilegible, no."""
    a, b = version_tupla(nueva), version_tupla(actual)
    if not a or not b:
        return False
    return _comparable(a) > _comparable(b)


def misma_version(a: Any, b: Any) -> bool:
    ta, tb = version_tupla(a), version_tupla(b)
    return bool(ta) and bool(tb) and _comparable(ta) == _comparable(tb)


def texto_version(texto: Any) -> str:
    """«v11.3» → «11.3» (lo que se enseña y se guarda en omitir_version)."""
    t = version_tupla(texto)
    return ".".join(str(n) for n in t) if t else ""


# ── GitHub Releases (la Lune instalada) ───────────────────────────────────────

REPO_GITHUB = "DiegoLizarraga/Lune_CD"
URL_API_ULTIMA = f"https://api.github.com/repos/{REPO_GITHUB}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO_GITHUB}/releases"
PREFIJO_DESCARGA = f"/{REPO_GITHUB}/releases/download/".lower()
TIMEOUT_HTTP = 10
TROZO = 256 * 1024                      # iter_content: 256 KiB por vuelta
MAX_REDIRECCIONES = 5
TAMANO_MAX = 1536 * 1024 * 1024         # un Setup de más de 1,5 GB no es mío
MARGEN_DISCO = 64 * 1024 * 1024         # lo que dejo libre además del Setup
MAX_NOTAS = 1200                        # notas del release en texto plano, recortadas
MAX_SHA_ASSET = 4096                    # el .sha256 es una línea
# github.com sirve el asset con una redirección a uno de sus servidores de descargas.
HOSTS_DESCARGA = frozenset({"github.com", "objects.githubusercontent.com",
                            "release-assets.githubusercontent.com"})
RE_ASSET = re.compile(r"^LuneCD-Setup-(\d+(?:\.\d+)*)\.exe$")
RE_SHA = re.compile(r"^[0-9a-f]{64}$")
# El Setup (packaging/lune.iss): sin preguntas, con su barra de progreso, cerrando lo que lo
# bloquee y volviéndome a abrir al terminar.
ARGS_SETUP = ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANZAR=1")
HORAS_ENTRE_COMPROBACIONES = 24


def _cabeceras(accept: str = "application/vnd.github+json") -> Dict[str, str]:
    # GitHub exige User-Agent; sin token (60 consultas por hora, de sobra).
    return {"User-Agent": f"LuneCD/{version_actual() or '?'} (+https://github.com/{REPO_GITHUB})",
            "Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}


def _get_por_defecto():
    import requests
    return requests.get


def destino_por_defecto() -> Path:
    """%LOCALAPPDATA%\\Lune CD\\cache\\actualizaciones (lo desechable; desde el código, el repo)."""
    from nucleo import rutas
    return rutas.local("cache", "actualizaciones")


def host_permitido(url: Any) -> bool:
    """¿HTTPS a github.com o a sus servidores de descargas, sin usuario ni puerto raro?"""
    try:
        p = urlparse(str(url or ""))
        puerto = p.port
    except ValueError:
        return False
    return (p.scheme == "https" and (p.hostname or "").lower() in HOSTS_DESCARGA
            and not p.username and not p.password and puerto in (None, 443))


def url_de_release(url: Any) -> bool:
    """¿Es un asset de un release de github.com/DiegoLizarraga/Lune_CD? (lo único que bajo)."""
    if not host_permitido(url):
        return False
    p = urlparse(str(url))
    return p.hostname.lower() == "github.com" and p.path.lower().startswith(PREFIJO_DESCARGA)


class ErrorDescarga(Exception):
    """Algo de la descarga no cuadra (host, tamaño, SHA-256…): el mensaje va al usuario."""


def _abrir(url: str, get, accept: str = "application/octet-stream"):
    """GET en streaming siguiendo las redirecciones A MANO: cada salto se valida (HTTPS y
    host de GitHub) ANTES de pedirlo. Devuelve la respuesta (200 o lo que diga GitHub)."""
    for _ in range(MAX_REDIRECCIONES + 1):
        if not host_permitido(url):
            raise ErrorDescarga("La descarga me mandaba fuera de GitHub; no la sigo.")
        r = get(url, headers=_cabeceras(accept), timeout=TIMEOUT_HTTP, stream=True,
                allow_redirects=False)
        estado = int(getattr(r, "status_code", 0) or 0)
        if estado in (301, 302, 303, 307, 308):
            destino = (getattr(r, "headers", None) or {}).get("Location") or ""
            _cerrar(r)
            if not destino:
                raise ErrorDescarga("GitHub me redirigió a ninguna parte.")
            url = urljoin(url, destino)
            continue
        return r
    raise ErrorDescarga("Demasiadas redirecciones al descargar; lo dejo.")


def _cerrar(r) -> None:
    try:
        r.close()
    except Exception:
        pass


def _limitado(r) -> bool:
    """¿403/429 por el límite de consultas sin token?"""
    estado = int(getattr(r, "status_code", 0) or 0)
    if estado == 429:
        return True
    cab = {str(k).lower(): str(v) for k, v in (getattr(r, "headers", None) or {}).items()}
    if cab.get("x-ratelimit-remaining") == "0":
        return True
    try:
        return "rate limit" in str(getattr(r, "text", "") or "").lower()
    except Exception:
        return False


def texto_plano(md: Any, maximo: int = MAX_NOTAS) -> str:
    """Las notas del release (Markdown) en texto plano y recortadas: solo lo nuevo (lo que va
    antes de «Cómo instalarme», que ya sé hacer sola), sin marcas ni enlaces."""
    s = str(md or "").replace("\r\n", "\n")
    corte = re.search(r"^#{1,6}\s*C[oó]mo instalarme", s, re.M | re.I)
    if corte:
        s = s[:corte.start()]
    s = re.sub(r"```.*?```", "", s, flags=re.S)
    s = re.sub(r"<[^>]{1,200}>", "", s)
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"(\*\*|__|`)", "", s)
    s = re.sub(r"^\s*[-*+]\s+", "· ", s, flags=re.M)
    s = "".join(ch for ch in s if ch in "\n\t" or ord(ch) >= 32)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    s = re.sub(r"^Lune CD v?\d+(?:\.\d+)*\s*\n+", "", s)      # el título ya lo digo yo
    if len(s) > maximo:
        s = s[:maximo].rstrip() + "…"
    return s


def _sha_del_digest(asset: dict) -> str:
    """El SHA-256 que GitHub calcula de cada asset ("digest": "sha256:…"), si viene."""
    d = str((asset or {}).get("digest") or "").strip().lower()
    if d.startswith("sha256:") and RE_SHA.match(d[7:]):
        return d[7:]
    return ""


def _sha_del_asset(asset: dict, nombre: str, get) -> str:
    """El SHA-256 del «<setup>.sha256» del release («<hash>  <nombre>»). "" si no vale."""
    url = str((asset or {}).get("browser_download_url") or "")
    if not url_de_release(url):
        return ""
    r = _abrir(url, get, accept="application/octet-stream")
    try:
        if int(getattr(r, "status_code", 0) or 0) != 200:
            return ""
        crudo = b""
        for trozo in r.iter_content(1024):
            crudo += trozo or b""
            if len(crudo) > MAX_SHA_ASSET:
                return ""
    finally:
        _cerrar(r)
    partes = crudo.decode("utf-8", "replace").strip().split()
    if not partes or not RE_SHA.match(partes[0].lower()):
        return ""
    if len(partes) > 1 and partes[-1].lstrip("*") != nombre:
        return ""                                   # el .sha256 de otro archivo
    return partes[0].lower()


def _omitir_de_config() -> str:
    try:
        from nucleo.config import Config
        return str(Config().get("actualizaciones", "omitir_version", "") or "")
    except Exception:
        return ""


def buscar_release(get=None, *, actual: Optional[str] = None, omitir: Optional[str] = None) -> Dict:
    """
    El último release de GitHub (sin borradores ni versiones de prueba) comparado con el mío.
    {ok, hay_novedades, nueva, omitida, version, actual, notas, fecha, pagina,
     asset: {nombre, url, tamano} | None, sha256, instalable, mensaje}
    `hay_novedades` es False si es la versión que me pediste saltar (config
    actualizaciones.omitir_version; `omitir` la sustituye). `get` es para los tests.
    """
    actual = version_actual() if actual is None else str(actual)
    omitir = _omitir_de_config() if omitir is None else str(omitir or "")
    res: Dict[str, Any] = {
        "ok": False, "hay_novedades": False, "nueva": False, "omitida": False,
        "version": "", "actual": actual, "notas": "", "fecha": "", "pagina": URL_RELEASES,
        "asset": None, "sha256": "", "instalable": False, "mensaje": "",
    }
    get = get or _get_por_defecto()
    try:
        r = get(URL_API_ULTIMA, headers=_cabeceras(), timeout=TIMEOUT_HTTP)
    except Exception:
        res["mensaje"] = "No pude hablar con GitHub (¿hay internet?). Lo intento más tarde."
        return res
    estado = int(getattr(r, "status_code", 0) or 0)
    if estado == 404:
        res["mensaje"] = "Todavía no hay ninguna versión mía publicada en GitHub."
        return res
    if estado in (403, 429) and _limitado(r):
        res["mensaje"] = ("GitHub me pidió un respiro (demasiadas consultas en una hora). "
                          "Lo vuelvo a mirar en un rato, sin prisa.")
        return res
    if estado != 200:
        res["mensaje"] = f"GitHub me contestó con un error ({estado}). Lo intento más tarde."
        return res
    try:
        datos = r.json()
    except Exception:
        datos = None
    if not isinstance(datos, dict):
        res["mensaje"] = "GitHub me contestó algo que no entiendo. Lo intento más tarde."
        return res
    pagina = str(datos.get("html_url") or "")
    if pagina.lower().startswith(URL_RELEASES.lower() + "/"):
        res["pagina"] = pagina
    if datos.get("draft") or datos.get("prerelease"):
        res.update(ok=True, mensaje=f"Estoy al día: tengo la {actual}.")
        return res
    version = texto_version(datos.get("tag_name"))
    if not version:
        res["mensaje"] = "El último release de GitHub no tiene un número de versión que entienda."
        return res
    res.update(ok=True, version=version, fecha=str(datos.get("published_at") or ""),
               notas=texto_plano(datos.get("body")))
    # El instalador de ESA versión (LuneCD-Setup-<v>.exe) y su SHA-256.
    assets = [a for a in (datos.get("assets") or []) if isinstance(a, dict)]
    nombre = f"LuneCD-Setup-{version}.exe"
    asset = next((a for a in assets if a.get("name") == nombre), None)
    if asset is None:
        asset = next((a for a in assets if RE_ASSET.match(str(a.get("name") or ""))
                      and misma_version(RE_ASSET.match(str(a.get("name"))).group(1), version)), None)
    if asset is not None:
        nombre = str(asset.get("name"))
        url = str(asset.get("browser_download_url") or "")
        try:
            tamano = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            tamano = 0
        if url_de_release(url) and 0 < tamano <= TAMANO_MAX:
            res["asset"] = {"nombre": nombre, "url": url, "tamano": tamano}
            sha = _sha_del_digest(asset)
            if not sha:
                del_sha = next((a for a in assets if a.get("name") == f"{nombre}.sha256"), None)
                if del_sha is not None:
                    try:
                        sha = _sha_del_asset(del_sha, nombre, get)
                    except Exception:
                        sha = ""
            res["sha256"] = sha
    res["instalable"] = bool(res["asset"] and res["sha256"])
    res["nueva"] = es_mas_nueva(version, actual)
    res["omitida"] = bool(res["nueva"] and omitir and misma_version(version, omitir))
    res["hay_novedades"] = bool(res["nueva"] and not res["omitida"])
    if res["hay_novedades"]:
        res["mensaje"] = f"Hay una versión nueva de mí: la {version} (tengo la {actual})."
    elif res["omitida"]:
        res["mensaje"] = f"La {version} es nueva, pero me pediste saltártela."
    else:
        res["mensaje"] = f"Estoy al día: tengo la {actual}, la última publicada."
    return res


def _sha_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(TROZO), b""):
            h.update(trozo)
    return h.hexdigest()


def _borrar(ruta: Path) -> None:
    try:
        ruta.unlink()
    except OSError:
        pass


def _borrar_viejas(destino: Path, conservar: str = "") -> None:
    """Los Setup y .part de otras versiones (o a medias) que quedaron de antes."""
    try:
        for p in destino.iterdir():
            if p.name == conservar or not p.is_file():
                continue
            if p.name.startswith("LuneCD-Setup-") and (p.suffix in (".exe", ".part")):
                _borrar(p)
    except OSError:
        pass


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB"


def descargar(info: Dict, on_progreso: Optional[Callable[[int, int], Any]] = None,
              cancelar: Optional[threading.Event] = None, destino: Optional[Path] = None,
              get=None) -> Dict:
    """
    Descarga el Setup de `info` (lo que dio buscar_release) a un .part y, solo si el tamaño y
    el SHA-256 cuadran, lo renombra. Borra las descargas viejas; si ya estaba descargado y
    comprobado, no lo baja otra vez. `on_progreso(bytes, total)` en cada trozo (quien pinta
    decide cada cuánto); `cancelar` corta la descarga y borra el .part.
    {ok, ruta, mensaje, cancelado}
    """
    def fallo(mensaje: str, **extra) -> Dict:
        return {"ok": False, "ruta": "", "mensaje": mensaje, "cancelado": False, **extra}

    info = info if isinstance(info, dict) else {}
    asset = info.get("asset") if isinstance(info.get("asset"), dict) else {}
    nombre = str(asset.get("nombre") or "")
    url = str(asset.get("url") or "")
    sha = str(info.get("sha256") or "").strip().lower()
    try:
        tamano = int(asset.get("tamano") or 0)
    except (TypeError, ValueError):
        tamano = 0
    if not RE_ASSET.match(nombre):
        return fallo("No encuentro mi instalador en ese release.")
    if not url_de_release(url):
        return fallo("Ese instalador no viene de mi página de GitHub; no lo descargo.")
    if not RE_SHA.match(sha):
        return fallo("No puedo comprobar que el instalador sea el de verdad (falta su SHA-256), "
                     "así que no lo descargo.")
    if not 0 < tamano <= TAMANO_MAX:
        return fallo("El tamaño del instalador no cuadra; no lo descargo.")
    destino = Path(destino) if destino is not None else destino_por_defecto()
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return fallo(f"No pude preparar la carpeta de descargas: {e}")
    final = destino / nombre
    parte = destino / (nombre + ".part")
    _borrar_viejas(destino, conservar=nombre)
    _borrar(parte)
    if final.exists():
        try:
            if final.stat().st_size == tamano and _sha_archivo(final) == sha:
                if on_progreso:
                    on_progreso(tamano, tamano)
                return {"ok": True, "ruta": str(final), "cancelado": False,
                        "mensaje": "Ya lo tenía descargado y comprobado."}
        except OSError:
            pass
        _borrar(final)
    try:
        libre = shutil.disk_usage(destino).free
    except OSError:
        libre = None
    if libre is not None and libre < tamano + MARGEN_DISCO:
        return fallo(f"No me cabe: necesito unos {_mb(tamano + MARGEN_DISCO)} libres en el disco.")

    get = get or _get_por_defecto()
    r = None
    try:
        r = _abrir(url, get)
        estado = int(getattr(r, "status_code", 0) or 0)
        if estado != 200:
            if estado in (403, 429) and _limitado(r):
                return fallo("GitHub me pidió un respiro. Lo intento en un rato, sin prisa.")
            return fallo(f"GitHub no me dejó descargarlo ({estado}). Lo intento más tarde.")
        h = hashlib.sha256()
        n = 0
        with open(parte, "wb") as f:
            for trozo in r.iter_content(TROZO):
                if cancelar is not None and cancelar.is_set():
                    break
                if not trozo:
                    continue
                n += len(trozo)
                if n > tamano:
                    raise ErrorDescarga("La descarga es más grande de lo que dice GitHub; la borré.")
                h.update(trozo)
                f.write(trozo)
                if on_progreso:
                    on_progreso(n, tamano)
        if cancelar is not None and cancelar.is_set():
            _borrar(parte)
            return {"ok": False, "ruta": "", "mensaje": "Cancelé la descarga.", "cancelado": True}
        if n != tamano:
            _borrar(parte)
            return fallo("La descarga se cortó a medias. Vuelve a intentarlo.")
        if h.hexdigest() != sha:
            _borrar(parte)
            return fallo("El instalador descargado no coincide con su huella SHA-256: lo borré "
                         "y no lo instalo.")
        os.replace(parte, final)
        return {"ok": True, "ruta": str(final), "cancelado": False,
                "mensaje": "Descargado y comprobado (SHA-256)."}
    except ErrorDescarga as e:
        _borrar(parte)
        return fallo(str(e))
    except Exception:
        _borrar(parte)
        return fallo("No pude descargarlo (¿se cortó internet?). Vuelve a intentarlo en un rato.")
    finally:
        if r is not None:
            _cerrar(r)


def orden_instalar(ruta: Any) -> List[str]:
    return [str(ruta), *ARGS_SETUP]


def instalar(ruta: Any, popen=None, sha256: str = "") -> bool:
    """
    Lanza el Setup descargado, desacoplado de Lune y en silencio (ARGS_SETUP: al terminar me
    vuelve a abrir). Solo un LuneCD-Setup-<v>.exe que exista; con `sha256`, lo comprueba otra
    vez. Devuelve True si arrancó. Quien llama cierra Lune de verdad (el «Salir» de la bandeja,
    no os._exit): el Setup espera a que me vaya (mutex LuneCD_Abierta). `popen` para los tests.
    """
    p = Path(str(ruta or ""))
    if not RE_ASSET.match(p.name) or not p.is_file():
        return False
    if sha256:
        try:
            if _sha_archivo(p) != str(sha256).strip().lower():
                return False
        except OSError:
            return False
    kw: Dict[str, Any] = {"cwd": str(p.parent), "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))
    else:
        kw["start_new_session"] = True
    try:
        (popen or subprocess.Popen)(orden_instalar(p), **kw)
    except Exception:
        return False
    return True


# ── Aviso al iniciar (las tres interfaces) ─────────────────────────────────────

def _cfg(config, clave: str, defecto: Any = None) -> Any:
    try:
        return config.get("actualizaciones", clave, defecto) if config is not None else defecto
    except Exception:
        return defecto


def _leer_fecha(texto: Any) -> Optional[datetime]:
    s = str(texto or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ahora(ahora: Optional[datetime] = None) -> datetime:
    return ahora if ahora is not None else datetime.now(timezone.utc)


def toca_comprobar(config, ahora: Optional[datetime] = None) -> bool:
    """¿Miro al iniciar? Con «Buscar al iniciar» encendido y como mucho una vez cada 24 h
    (actualizaciones.ultima_comprobacion). Una fecha del futuro (reloj cambiado) no bloquea."""
    if not bool(_cfg(config, "comprobar_al_iniciar", True)):
        return False
    ultima = _leer_fecha(_cfg(config, "ultima_comprobacion", ""))
    if ultima is None:
        return True
    ahora = _ahora(ahora)
    if ultima > ahora + timedelta(hours=1):
        return True
    return ahora - ultima >= timedelta(hours=HORAS_ENTRE_COMPROBACIONES)


def marcar_comprobacion(config, ahora: Optional[datetime] = None) -> str:
    """Apunta que miré ahora (ISO-8601 UTC, «2026-09-30T18:00:00Z»). Las ventanas lo llaman
    desde el hilo de Qt. Devuelve lo escrito ("" si no se pudo)."""
    texto = _ahora(ahora).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        config.set("actualizaciones", "ultima_comprobacion", texto)
    except Exception:
        return ""
    return texto


def buscar_novedades(modo_: Optional[str] = None, *, get=None, comprobar_git=None,
                     rama: Optional[str] = None, actual: Optional[str] = None,
                     omitir: Optional[str] = None) -> Dict:
    """
    ¿Hay algo nuevo? Según el modo: instalada → el release de GitHub (buscar_release);
    git → comprobar() (commits nuevos en el remoto); carpeta → el release, solo para avisar
    (con el enlace a la página). Siempre lleva "modo" y "pagina". No lanza.
    """
    modo_ = modo_ or modo()
    try:
        if modo_ == MODO_GIT:
            res = dict((comprobar_git or comprobar)(rama or None))
            res.setdefault("version", "")
            res["pagina"] = URL_RELEASES
        else:
            res = buscar_release(get, actual=actual, omitir=omitir)
            if modo_ == MODO_CARPETA:
                res["instalable"] = False
    except Exception as e:
        res = {"ok": False, "hay_novedades": False, "pagina": URL_RELEASES,
               "mensaje": f"No pude buscar actualizaciones: {e}"}
    res["modo"] = modo_
    return res


def texto_aviso(res: Dict, donde: str = "ajustes") -> str:
    """La línea del aviso de versión nueva. `donde`: "ajustes" (ventanas) o "patata"."""
    res = res if isinstance(res, dict) else {}
    ir = "Escribe /actualizar para verla." if donde == "patata" else "Ajustes → Sistema → Actualizaciones"
    if res.get("modo") == MODO_GIT:
        n = int(res.get("pendientes") or 0) or len(res.get("commits") or [])
        ir = "Escribe /actualizar para verlos." if donde == "patata" else ir
        return f"Hay {n} cambio(s) nuevo(s) de mí en GitHub. {ir}"
    version = res.get("version") or "?"
    if res.get("modo") == MODO_CARPETA:
        return f"Hay una versión nueva de mí ({version}). Descárgala en {res.get('pagina') or URL_RELEASES}"
    return f"Hay una versión nueva de mí ({version}). {ir}"
