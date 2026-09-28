"""
lune_core/minecraft_proceso.py — Lanza, habla con y para el bot de Minecraft
(`minecraft-bot/`, Node) como PROCESO HIJO. Sin Qt: se prueba en seco.

Canal (el mismo patrón que servicios/telegram_worker.py y telegram-bot-or/ordenes.js)
------------------------------------------------------------------------------------
  · Lanzamiento: `node [--permission --allow-fs-read=<minecraft-bot>] src/bot.js`,
    SIN shell ni `npm start` (con shell, terminate() solo mataba cmd.exe y dejaba
    node huérfano). Sin ventana de consola.
  · Token nuevo en cada lanzamiento (`secrets.token_hex(16)`) en LUNE_MC_TOKEN. El
    entorno del hijo NO hereda ninguna LUNE_* ni NODE_OPTIONS de fuera.
  · Bot → Lune: líneas que EMPIEZAN por «@@LUNE <token> <json ASCII>» (≤8 KB).
    La marca solo cuenta al principio de la línea: un jugador que escriba
    «@@LUNE …» en el chat del juego no puede colarla (y no sabe el token). Lo que
    no es un mensaje válido va a `on_log` (≤300 caracteres, token y clave del
    modelo enmascarados); una línea con la marca que no valida se descarta.
  · Lune → bot: la PRIMERA línea de stdin es la configuración ({"tipo":"config",…},
    con la clave del modelo si hace falta: nunca va en el entorno ni al log);
    luego orden, decir, pausa_llm, pausa_autonomo, estado y salir. Las escribe un
    hilo «lune-mc-stdin» desde una cola: `enviar()` nunca bloquea la interfaz.
  · Parar: «salir» → espera → cerrar stdin (el bot sale solo al verlo) →
    terminate → matar el árbol. Idempotente.
  · En Windows cada hijo (el bot y npm) va en un Job con KILL_ON_JOB_CLOSE: matar
    el Job mata también sus nietos (node lanzado por un node.cmd de un gestor de
    versiones, los hijos de npm) y, si Lune se cierra o se cae, Windows cierra el
    Job y no queda nada huérfano. Sin Job (no se pudo crear): `taskkill /T /F /PID`
    del PID del hijo, nunca por nombre.
  · `ruta_node()`: si el PATH da un node.cmd/.bat (gestores de versiones), se usa el
    node.exe de verdad si está en el PATH.

Instalación (D3): SOLO por acción explícita del usuario (botón «Instalar el bot»),
nunca desde una herramienta del modelo: `npm ci --omit=optional --ignore-scripts`
con el package-lock.json del repo (integridad sha512, versiones exactas, sin
scripts de instalación ni visor). Cancelable (`cancelar_instalacion()`: detener y
salir la cortan, matando npm y sus hijos) y de una en una en la carpeta: la marca
`minecraft-bot/.instalando` (con el PID de Lune y el de npm) va CERRADA con un
cerrojo del sistema mientras dura; otra ventana u otra Lune (patata) ve el cerrojo
y no lanza otro npm ci. Si Lune muere, el sistema suelta el cerrojo solo (sin mirar
PIDs de nadie: un PID reciclado no puede dejarla «instalando» para siempre). Con el
bot en marcha no se instala (npm ci borra node_modules, que el bot está usando).

Hardening: con un Node que tenga el modelo de permisos (`--permission`, Node
22.13+/23.5+) el hijo solo puede LEER su carpeta: no escribe en disco ni crea
procesos o workers. Se detecta mirando `node --help`; si ese Node no lo tiene,
arranca sin él (el bot sigue siendo un cliente de red como otro jugador).

Anticheat: el bot es un cliente de red; nada aquí abre handles al proceso del juego
(el Job y taskkill solo tocan los hijos que lanza Lune, por su PID).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger("lune.minecraft")

RAIZ = Path(__file__).resolve().parent.parent
BOT_DIR = RAIZ / "minecraft-bot"
MARCA = "@@LUNE"
MAX_LINEA = 8192                    # bot → Lune
MAX_ENTRADA = 32768                 # Lune → bot (igual que canal.js)
MAX_LOG = 300
ENV_TOKEN = "LUNE_MC_TOKEN"
ENV_HIJO = "LUNE_BOT_HIJO"
NODE_MINIMO = 18
TIMEOUT_INSTALAR_S = 900
COLA_ENVIOS = 256
ESPERA_ESCRITOR_S = 1.0
ARGS_NPM_CI = ("ci", "--omit=optional", "--ignore-scripts", "--no-audit", "--no-fund")
TIPOS_BOT = frozenset({"listo", "conectado", "desconectado", "estado", "evento", "chat", "respuesta", "error"})
TIPOS_A_BOT = frozenset({"config", "orden", "decir", "pausa_llm", "pausa_autonomo", "estado", "salir"})
ESTILOS = ("personaje", "sobrio")
PROVEEDORES = ("ollama", "openrouter", "compat")
URL_OPENROUTER = "https://openrouter.ai/api/v1"
MAX_PERSONA = 2000                  # en unidades UTF-16, como las cuenta config.js (.length)
MARCA_INSTALANDO = ".instalando"
AVISO_BOT_VIVO = "Desconecta el bot antes de reinstalarlo (npm borraría los archivos que está usando)."

AVISO_INSTALAR = "Instala el bot en Ajustes → Minecraft (descarga ~400 MB)."
AVISO_SIN_NODE = "Hace falta Node.js 18 o más nuevo (nodejs.org) para el bot de Minecraft."
AVISO_SIN_DUENO = ("Pon tu nick de Minecraft (dueño) en Ajustes → Minecraft: "
                   "el bot solo obedece a su dueño.")

SIN_CONSOLA: Dict[str, Any] = {}
if os.name == "nt":
    SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}

_NICK = re.compile(r"[A-Za-z0-9_]{3,16}")
_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")
_ETIQUETA = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4 = re.compile(r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}")
_IPV6 = re.compile(r"[0-9A-Fa-f:]{2,39}")
_ID_ORDEN = re.compile(r"[A-Za-z0-9_\-]{1,40}")
_VERSION_NODE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_KEEP_ALIVE = re.compile(r"-?\d+(?:\.\d+)?[smh]?")


# ── Validación ─────────────────────────────────────────────────────────────────

def nick_valido(s: Any) -> Optional[str]:
    """Un nick de Minecraft (3–16 letras ASCII, números o _) o None."""
    t = str(s or "").strip() if isinstance(s, (str, int)) else ""
    return t if _NICK.fullmatch(t) else None


def validar_host(s: Any) -> Optional[str]:
    """Nombre de equipo, dominio, IPv4 o IPv6 (≤253). Nada de esquemas, rutas ni espacios."""
    if not isinstance(s, str):
        return None
    h = s.strip()
    if not h or len(h) > 253:
        return None
    if _IPV4.fullmatch(h):
        return h
    if ":" in h:
        return h if _IPV6.fullmatch(h) and h.count(":") >= 2 else None
    if all(_ETIQUETA.fullmatch(e) for e in h.split(".")):
        return h
    return None


def nick_desde_nombre(nombre: Any) -> str:
    """Nick válido a partir del nombre del personaje («Lúne» → «Lune»; «Mi» → «Mi_bot»)."""
    t = unicodedata.normalize("NFKD", str(nombre or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9_]+", "_", t).strip("_")[:16]
    if len(t) < 3:
        t = (t + "_bot") if t else "Lune_bot"
    return t[:16]


def version_node(texto: Any) -> Optional[Tuple[int, int, int]]:
    m = _VERSION_NODE.search(str(texto or ""))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _entero(v: Any, minimo: int, maximo: int, defecto: int) -> int:
    if isinstance(v, bool):
        return defecto
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, n))


def largo_utf16(texto: str) -> int:
    """Lo que mide `texto.length` en JavaScript (un emoji fuera del BMP cuenta 2)."""
    return len(texto) + sum(1 for c in texto if ord(c) > 0xFFFF)


def _recortar(texto: str, tope: int) -> str:
    """≤ `tope` unidades UTF-16 (lo que mide config.js), cortando en un espacio si se puede
    y nunca a mitad de un emoji."""
    texto = str(texto or "").strip()
    if largo_utf16(texto) <= tope:
        return texto
    n = unidades = 0
    for n, c in enumerate(texto):
        unidades += 2 if ord(c) > 0xFFFF else 1
        if unidades > tope:
            break
    corte = texto.rfind(" ", 0, n)
    return texto[: corte if corte > n // 2 else n].rstrip()


def _persona(personaje: Optional[dict]) -> dict:
    """{nombre, prompt ≤2000, frases} del personaje. SIN la memoria de Lune: el chat
    de Minecraft es público."""
    p = personaje if isinstance(personaje, dict) else {}
    nombre = _recortar(re.sub(r"[\x00-\x1f\x7f]", "", str(p.get("nombre") or "Lune")), 40) or "Lune"
    try:
        from nucleo.personajes import build_system_prompt
        prompt = build_system_prompt(p) if p else ""
    except Exception:
        prompt = str(p.get("systemPrompt") or "")
    frases = p.get("frases_minecraft")
    if not isinstance(frases, dict):
        frases = {}
    limpias: Dict[str, List[str]] = {}
    for cat, lista in list(frases.items())[:40]:
        if isinstance(cat, str) and re.fullmatch(r"[A-Za-z_]{1,24}", cat) and isinstance(lista, list):
            ok = [_recortar(f, 120) for f in lista if isinstance(f, str) and f.strip()][:12]
            if ok:
                limpias[cat] = ok
    return {"nombre": nombre, "prompt": _recortar(prompt, MAX_PERSONA), "frases": limpias}


def config_llm(datos_mod: Any = None) -> Optional[dict]:
    """El modelo propio del bot desde datos.json: `bot.proveedor` (el mismo que el bot de
    Telegram) y las mismas claves de `modelos` que la app. None si no hay modelo."""
    if datos_mod is None:
        from nucleo import datos as datos_mod
    try:
        prov = str((datos_mod.get_bot() or {}).get("proveedor") or "openrouter").strip().lower()
    except Exception:
        prov = "openrouter"
    if prov not in PROVEEDORES:
        prov = "openrouter"
    try:
        if prov == "ollama":
            ka = str(datos_mod.ollama_keep_alive() or "30m").strip()
            return {"proveedor": "ollama", "url": str(datos_mod.ollama_url() or "http://localhost:11434").rstrip("/"),
                    "modelo": str(datos_mod.ollama_model() or ""), "clave": "",
                    "keep_alive": ka if _KEEP_ALIVE.fullmatch(ka) else "30m",
                    "num_ctx": _entero(datos_mod.ollama_num_ctx(), 512, 262144, 8192),
                    "timeout_ms": _entero(datos_mod.ollama_timeout(), 5, 120, 60) * 1000}
        if prov == "compat":
            url = str(datos_mod.compat_url() or "")
            try:
                from servicios.ai_manager import base_compat
                url = base_compat(url)
            except Exception:
                url = url.rstrip("/")
            return {"proveedor": "compat", "url": url, "modelo": str(datos_mod.compat_model() or ""),
                    "clave": str(datos_mod.compat_key() or ""), "keep_alive": "30m", "num_ctx": 8192,
                    "timeout_ms": _entero(datos_mod.compat_timeout(), 5, 120, 60) * 1000}
        return {"proveedor": "openrouter", "url": URL_OPENROUTER, "modelo": str(datos_mod.openrouter_model() or ""),
                "clave": str(datos_mod.openrouter_key() or ""), "keep_alive": "30m", "num_ctx": 8192,
                "timeout_ms": 30000}
    except Exception:
        _log.exception("minecraft: no pude leer el modelo del bot")
        return None


def _llm_valido(llm: Any) -> Optional[dict]:
    """El LLM tal como lo acepta config.js, o None (sin cerebro: órdenes y reflejos siguen)."""
    if not isinstance(llm, dict):
        return None
    prov = str(llm.get("proveedor") or "").lower()
    url = str(llm.get("url") or "").strip().rstrip("/")
    modelo = str(llm.get("modelo") or "").strip()[:200]
    clave = str(llm.get("clave") or "").strip()[:500]
    if prov not in PROVEEDORES or not re.match(r"https?://", url) or not modelo:
        return None
    if prov == "openrouter" and not clave:
        return None
    ka = str(llm.get("keep_alive") or "30m").strip()
    return {"proveedor": prov, "url": url, "modelo": modelo, "clave": clave,
            "keep_alive": ka if _KEEP_ALIVE.fullmatch(ka) else "30m",
            "num_ctx": _entero(llm.get("num_ctx"), 512, 262144, 8192),
            "timeout_ms": _entero(llm.get("timeout_ms"), 1000, 300000, 20000)}


def config_bot(datos_mc: dict, personaje: Optional[dict], llm: Optional[dict], *,
               estilo: Optional[str] = None) -> dict:
    """La primera línea para el bot ({"tipo":"config", …}). ValueError con el texto
    para el usuario si falta algo (dueño, servidor…). El nick es `usuario` o el nombre
    del personaje saneado (+"_bot" si coincide con el dueño)."""
    d = datos_mc if isinstance(datos_mc, dict) else {}
    host = validar_host(str(d.get("host") or "localhost"))
    if not host:
        raise ValueError("El servidor de Minecraft no es un nombre ni una IP válidos.")
    puerto = d.get("port", 25565)
    try:
        puerto = int(puerto)
    except (TypeError, ValueError):
        puerto = 0
    if not 1 <= puerto <= 65535:
        raise ValueError("El puerto del servidor tiene que estar entre 1 y 65535.")
    version = str(d.get("version") or "").strip()
    if version and not _VERSION.fullmatch(version):
        raise ValueError("La versión tiene que ser como 1.21.1 (o vacía para autodetectarla).")
    dueno = nick_valido(d.get("dueno"))
    if not dueno:
        raise ValueError(AVISO_SIN_DUENO)
    per = _persona(personaje)
    nick = nick_valido(d.get("usuario")) or nick_desde_nombre(per["nombre"])
    if nick.lower() == dueno.lower():
        nick = (nick[:12] + "_bot")
        if nick.lower() == dueno.lower():
            nick = "Lune_bot"
    est = str(estilo or d.get("estilo_frases") or "personaje").strip().lower()
    return {
        "tipo": "config",
        "host": host,
        "port": puerto,
        "version": version,
        "nick": nick,
        "dueno": dueno,
        "solo_dueno": d.get("solo_dueno", True) is not False,
        "defender": d.get("defender", True) is not False,
        "pensar_cada_s": _entero(d.get("pensar_cada_s"), 30, 3600, 45),
        "estilo": est if est in ESTILOS else "personaje",
        "persona": per,
        "llm": _llm_valido(llm),
        "pausa_autonomo": False,
        "pausa_llm": False,
    }


# ── Hijos: Job de Windows, matar el árbol y la marca de «instalando» ──────────

class _Job:
    """Job object de Windows con KILL_ON_JOB_CLOSE para UN hijo de Lune (y lo que ese hijo
    lance): `matar()` mata el árbol entero y, si Lune se cierra o se cae, Windows cierra el
    Job y mata lo que quede. `para(p)` → None fuera de Windows o si no se puede (entonces
    se mata con taskkill /T por el PID del hijo)."""

    def __init__(self, handle: int, k32: Any):
        self._h: Optional[int] = handle
        self._k32 = k32

    @classmethod
    def para(cls, proceso: Any) -> "Optional[_Job]":
        h_proc = getattr(proceso, "_handle", None)
        if os.name != "nt" or not h_proc:
            return None
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class Basica(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class Io(ctypes.Structure):
                _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount",
                                                           "OtherOperationCount", "ReadTransferCount",
                                                           "WriteTransferCount", "OtherTransferCount")]

            class Extendida(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", Basica), ("IoInfo", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
            k32.SetInformationJobObject.restype = wintypes.BOOL
            k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
            k32.AssignProcessToJobObject.restype = wintypes.BOOL
            k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
            k32.TerminateJobObject.restype = wintypes.BOOL
            k32.CloseHandle.argtypes = (wintypes.HANDLE,)
            k32.CloseHandle.restype = wintypes.BOOL
            h = k32.CreateJobObjectW(None, None)
            if not h:
                return None
            info = Extendida()
            info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)) or \
                    not k32.AssignProcessToJobObject(h, int(h_proc)):
                k32.CloseHandle(h)
                return None
            return cls(h, k32)
        except Exception:
            _log.debug("minecraft: sin Job de Windows", exc_info=True)
            return None

    def matar(self) -> bool:
        h = self._h
        if not h:
            return False
        try:
            return bool(self._k32.TerminateJobObject(h, 1))
        except Exception:
            return False

    def cerrar(self) -> None:
        """Cierra el Job (lo que quede dentro muere: KILL_ON_JOB_CLOSE)."""
        h, self._h = self._h, None
        if h:
            try:
                self._k32.CloseHandle(h)
            except Exception:
                pass


def matar_arbol(proceso: Any, job: "Optional[_Job]" = None, *, ejecutar: Callable[..., Any] = subprocess.run) -> None:
    """Mata `proceso` (un hijo de Lune) y sus descendientes: el Job si lo hay; si no, en
    Windows `taskkill /T /F /PID <su pid>` (nunca por nombre) y, como último recurso, kill()."""
    if proceso is None:
        return
    try:
        vivo = proceso.poll() is None
    except Exception:
        vivo = True
    if job is not None and job.matar():
        return
    if not vivo:
        return
    pid = getattr(proceso, "pid", None)
    if os.name == "nt" and isinstance(pid, int) and pid > 0:
        try:
            ejecutar(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=10, **SIN_CONSOLA)
        except Exception:
            pass
    try:
        if proceso.poll() is None:
            proceso.kill()
    except Exception:
        pass


class _Cerrojo:
    """La marca `minecraft-bot/.instalando`: un archivo con el PID de Lune (y el de npm) y un
    cerrojo del sistema encima mientras se instala. Otro proceso u otra ventana que intente
    cogerlo falla → «ya se está instalando». Si Lune muere, el sistema suelta el cerrojo."""

    BYTE = 1 << 20                  # se cierra un byte lejos del texto (que se pueda leer)

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self._f: Any = None

    def _bloquear(self, f: Any) -> bool:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(self.BYTE)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)      # por descriptor, no por proceso
            return True
        except OSError:
            return False

    def tomar(self) -> bool:
        if self._f is not None:
            return True
        try:
            f = open(self.ruta, "a+b")
        except OSError:
            return True                 # carpeta de solo lectura: sin marca, como antes
        if not self._bloquear(f):
            f.close()
            return False
        self._f = f
        self.anotar(None)
        return True

    def anotar(self, pid_npm: Optional[int]) -> None:
        f = self._f
        if f is None:
            return
        try:
            f.seek(0)
            f.truncate()
            f.write(json.dumps({"lune": os.getpid(), "npm": pid_npm, "t": int(time.time())}).encode("ascii"))
            f.flush()
        except OSError:
            pass

    def ocupado(self) -> bool:
        """¿Lo tiene cogido otro (otra ventana u otra Lune)?"""
        if self._f is not None or not self.ruta.is_file():
            return False
        try:
            f = open(self.ruta, "a+b")
        except OSError:
            return False
        try:
            libre = self._bloquear(f)
            if libre:
                self._soltar_de(f)
            return not libre
        finally:
            f.close()

    def _soltar_de(self, f: Any) -> None:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(self.BYTE)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    def soltar(self) -> None:
        f, self._f = self._f, None
        if f is None:
            return
        self._soltar_de(f)
        try:
            f.close()
        except OSError:
            pass
        try:
            self.ruta.unlink()
        except OSError:
            pass                        # otra ventana la está mirando justo ahora: da igual


# ── Proceso ────────────────────────────────────────────────────────────────────

def _llamar(fn: Optional[Callable], *args) -> None:
    if not callable(fn):
        return
    try:
        fn(*args)
    except Exception:
        _log.exception("minecraft: el receptor de %s falló", getattr(fn, "__name__", "?"))


class ProcesoBot:
    """El bot de Minecraft como proceso hijo (ver el docstring del módulo).

    Los avisos (`on_evento(dict)`, `on_log(str)`, `on_fin(codigo)`) llegan desde el
    hilo lector «lune-mc-stdout»: quien los use en Qt tiene que pasarlos a su hilo.
    """

    def __init__(self, carpeta: Any = BOT_DIR, *, node: Optional[str] = None, npm: Any = None,
                 popen: Callable[..., Any] = subprocess.Popen, ejecutar: Callable[..., Any] = subprocess.run,
                 on_evento: Optional[Callable[[dict], None]] = None, on_log: Optional[Callable[[str], None]] = None,
                 on_fin: Optional[Callable[[Optional[int]], None]] = None,
                 which: Callable[[str], Optional[str]] = shutil.which):
        self.carpeta = Path(carpeta)
        self._node = node
        self._npm = npm
        self._popen = popen
        self._ejecutar = ejecutar
        self._which = which
        self.on_evento = on_evento
        self.on_log = on_log
        self.on_fin = on_fin
        self._lock = threading.Lock()
        self._proceso: Any = None
        self._token = ""
        self._secretos: List[str] = []
        self._cola: "queue.Queue" = queue.Queue(maxsize=COLA_ENVIOS)
        self._escritor: Optional[threading.Thread] = None
        self._roto_de: Any = None
        self._req: Optional[dict] = None
        self._permisos_cache: Optional[List[str]] = None
        self._instalando = False
        self._npm_hijo: Any = None             # (Popen, _Job) de npm ci mientras dura
        self._cancelada = False
        self._jobs: Dict[int, "_Job"] = {}     # id(Popen del bot) → su Job
        self._cerrojo = _Cerrojo(self.carpeta / MARCA_INSTALANDO)

    # ── Requisitos ─────────────────────────────────────────────────────────────
    def ruta_node(self) -> Optional[str]:
        """node del PATH. Si es un node.cmd/.bat (gestores de versiones), el node.exe de verdad
        si también está en el PATH (con el .cmd, terminate() mataría solo cmd.exe; el Job y
        taskkill /T igualmente matan el árbol)."""
        if self._node:
            return self._node
        w = self._which("node")
        if w and os.name == "nt" and str(w).lower().endswith((".cmd", ".bat")):
            exe = self._which("node.exe")
            if exe:
                return exe
        return w

    def _comando_npm(self) -> Optional[List[str]]:
        """npm sin shell: `node <npm-cli.js>` si viene junto a node; si no, el npm del PATH."""
        if self._npm:
            return list(self._npm) if isinstance(self._npm, (list, tuple)) else [str(self._npm)]
        node = self.ruta_node()
        if node:
            cli = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if cli.is_file():
                return [node, str(cli)]
        w = self._which("npm")
        return [w] if w else None

    def instalado(self) -> bool:
        return (self.carpeta / "node_modules" / "mineflayer" / "package.json").is_file()

    def requisitos(self, refrescar: bool = False) -> dict:
        """{node: 'v24.19.0'|None, node_ok (≥18), npm: bool, instalado: bool}."""
        if self._req is not None and not refrescar:
            r = dict(self._req)
            r["instalado"] = self.instalado()
            return r
        node = self.ruta_node()
        ver = None
        if node:
            try:
                res = self._ejecutar([node, "--version"], capture_output=True, text=True, timeout=10, **SIN_CONSOLA)
                salida = str(getattr(res, "stdout", "") or "").strip()
                if version_node(salida):
                    ver = salida.splitlines()[0][:20]
            except Exception:
                ver = None
        v = version_node(ver)
        self._req = {"node": ver, "node_ok": bool(v and v[0] >= NODE_MINIMO), "npm": bool(self._comando_npm())}
        r = dict(self._req)
        r["instalado"] = self.instalado()
        return r

    def permisos(self) -> List[str]:
        """Banderas del modelo de permisos de Node si este Node lo tiene (mirando `node --help`)."""
        if self._permisos_cache is not None:
            return list(self._permisos_cache)
        flags: List[str] = []
        node = self.ruta_node()
        if node:
            try:
                res = self._ejecutar([node, "--help"], capture_output=True, text=True, timeout=10, **SIN_CONSOLA)
                ayuda = str(getattr(res, "stdout", "") or "")
            except Exception:
                ayuda = ""
            if re.search(r"(?m)^\s*--permission\b", ayuda):
                flags = ["--permission", f"--allow-fs-read={self.carpeta.resolve()}"]
                if re.search(r"(?m)^\s*--allow-net\b", ayuda):
                    flags.append("--allow-net")
        self._permisos_cache = flags
        return list(flags)

    # ── Instalar (solo con el botón) ───────────────────────────────────────────
    @property
    def instalando(self) -> bool:
        """Esta instancia instala, u otra (otra ventana, otra Lune: la marca con cerrojo)."""
        return self._instalando or self._cerrojo.ocupado()

    def instalar(self, cancelar: Optional[Callable[[], bool]] = None) -> Tuple[bool, str]:
        """`npm ci --omit=optional --ignore-scripts --no-audit --no-fund` en la carpeta
        del bot, sin ventana, con tope de 15 min y cancelable (`cancelar_instalacion()`).
        → (ok, texto). Bloquea: en un hilo."""
        if self._instalando:
            return False, "Ya se está instalando."
        if self.vivo:
            return False, AVISO_BOT_VIVO
        req = self.requisitos(refrescar=True)
        if not req["node_ok"]:
            return False, AVISO_SIN_NODE
        npm = self._comando_npm()
        if not npm:
            return False, "No encuentro npm (viene con Node.js)."
        if not (self.carpeta / "package-lock.json").is_file():
            return False, "Falta minecraft-bot/package-lock.json: no instalo sin versiones fijas."
        if callable(cancelar) and cancelar():
            return False, "Instalación cancelada."
        if not self._cerrojo.tomar():
            return False, "Ya se está instalando (desde otra ventana de Lune)."
        self._instalando = True
        self._cancelada = False
        try:
            return self._npm_ci(npm)
        finally:
            with self._lock:
                self._npm_hijo = None
            self._instalando = False
            self._cerrojo.soltar()

    def _npm_ci(self, npm: List[str]) -> Tuple[bool, str]:
        try:
            p = self._popen(npm + list(ARGS_NPM_CI), cwd=str(self.carpeta), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=self._entorno(None), **SIN_CONSOLA)
        except Exception as e:
            return False, f"No pude lanzar npm: {e}"[:300]
        job = _Job.para(p)
        with self._lock:
            self._npm_hijo = (p, job)
            cancelada = self._cancelada
        self._cerrojo.anotar(getattr(p, "pid", None))
        if cancelada:
            matar_arbol(p, job, ejecutar=self._ejecutar)
        try:
            try:
                salida, errores = p.communicate(timeout=TIMEOUT_INSTALAR_S)
            except subprocess.TimeoutExpired:
                matar_arbol(p, job, ejecutar=self._ejecutar)
                try:
                    p.communicate(timeout=10)
                except Exception:
                    pass
                return False, "npm tardó más de 15 minutos: lo corté. Prueba otra vez con mejor conexión."
            except Exception as e:
                matar_arbol(p, job, ejecutar=self._ejecutar)
                return False, f"npm falló: {e}"[:300]
        finally:
            if job is not None:
                job.cerrar()
        if self._cancelada:
            return False, "Instalación cancelada."
        codigo = getattr(p, "returncode", 1)
        if codigo == 0 and self.instalado():
            return True, "Bot de Minecraft instalado."
        texto = (str(errores or "") + "\n" + str(salida or "")).strip()
        ultimas = " · ".join(l.strip() for l in texto.splitlines()[-4:] if l.strip())
        return False, f"npm ci falló (código {codigo}): {ultimas}"[:400]

    def cancelar_instalacion(self) -> bool:
        """Corta un npm ci en marcha de ESTA instancia (y sus hijos). → True si había uno."""
        with self._lock:
            self._cancelada = True
            hijo = self._npm_hijo
        if not self._instalando:
            self._cancelada = False
            return False
        if hijo is not None:
            matar_arbol(hijo[0], hijo[1], ejecutar=self._ejecutar)
        return True

    # ── Arrancar ───────────────────────────────────────────────────────────────
    @property
    def vivo(self) -> bool:
        with self._lock:
            p = self._proceso
        if p is None:
            return False
        try:
            return p.poll() is None
        except Exception:
            return False

    def _entorno(self, token: Optional[str]) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith("LUNE_") and k.upper() != "NODE_OPTIONS"}
        if token:
            env[ENV_TOKEN] = token
            env[ENV_HIJO] = "1"
        return env

    def arrancar(self, cfg: dict, *, probar: bool = False) -> Tuple[bool, str]:
        """Lanza el bot y le manda `cfg` como primera línea. → (ok, texto)."""
        if self.vivo:
            return False, "El bot ya está en marcha."
        if not isinstance(cfg, dict):
            return False, "Configuración del bot inválida."
        node = self.ruta_node()
        if not node:
            return False, AVISO_SIN_NODE
        if not (self.carpeta / "src" / "bot.js").is_file():
            return False, "Falta minecraft-bot/src/bot.js."
        if not probar and not self.instalado():
            return False, AVISO_INSTALAR
        token = secrets.token_hex(16)
        linea_cfg = json.dumps(dict(cfg, tipo="config"), ensure_ascii=True) + "\n"
        if len(linea_cfg) > MAX_ENTRADA:
            return False, "La configuración del bot es demasiado grande (¿persona muy larga?)."
        clave = str(((cfg.get("llm") or {}) if isinstance(cfg.get("llm"), dict) else {}).get("clave") or "")
        args = [node, *self.permisos(), os.path.join("src", "bot.js")] + (["--probar"] if probar else [])
        try:
            p = self._popen(args, cwd=str(self.carpeta), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                            env=self._entorno(token), **SIN_CONSOLA)
        except Exception as e:
            return False, f"No pude lanzar el bot: {e}"[:300]
        job = _Job.para(p)
        with self._lock:
            self._proceso = p
            if job is not None:
                self._jobs[id(p)] = job
            self._token = token
            self._secretos = [s for s in (token, clave) if s and len(s) >= 6]
            self._roto_de = None
            self._encolar(p, linea_cfg)
        hilo = threading.Thread(target=self._leer_salida, args=(p,), name="lune-mc-stdout", daemon=True)
        hilo.start()
        return True, "Arrancando el bot…"

    # ── Salida del bot ─────────────────────────────────────────────────────────
    def _sin_secretos(self, texto: str) -> str:
        for s in self._secretos:
            texto = texto.replace(s, "***")
        return texto

    def leer_mensaje(self, linea: str) -> Optional[dict]:
        """El mensaje de una línea «@@LUNE <token> <json>» de ESTE bot, o None."""
        if not self._token or not isinstance(linea, str) or len(linea) > MAX_LINEA:
            return None
        if not linea.startswith(MARCA + " "):
            return None
        partes = linea.split(" ", 2)
        if len(partes) != 3:
            return None
        if not secrets.compare_digest(partes[1].encode("utf-8", "replace"), self._token.encode("ascii")):
            return None
        try:
            msg = json.loads(partes[2])
        except ValueError:
            return None
        if not isinstance(msg, dict) or msg.get("tipo") not in TIPOS_BOT:
            return None
        return msg

    def procesar_linea(self, linea: Any) -> None:
        """Una línea del stdout del bot: mensaje (→ on_evento) o log (→ on_log, sin secretos)."""
        linea = str(linea or "").rstrip("\r\n")
        if not linea:
            return
        if MARCA in linea:
            msg = self.leer_mensaje(linea)
            if msg is not None:
                _llamar(self.on_evento, msg)
            return                              # una marca mal puesta nunca va al log
        _llamar(self.on_log, self._sin_secretos(linea)[:MAX_LOG])

    def _leer_salida(self, p: Any) -> None:
        try:
            for linea in p.stdout:
                self.procesar_linea(linea)
        except (OSError, ValueError):
            pass
        codigo = None
        try:
            codigo = p.wait(timeout=5)
        except Exception:
            codigo = None
        with self._lock:
            if self._proceso is p:
                self._proceso = None
            job = self._jobs.pop(id(p), None)
        if job is not None:
            job.cerrar()                        # lo que el bot hubiera dejado vivo, fuera
        _llamar(self.on_fin, codigo)

    # ── Hacia el bot (stdin) ───────────────────────────────────────────────────
    def _encolar(self, p: Any, linea: str) -> bool:
        """Con self._lock tomado."""
        try:
            self._cola.put_nowait((p, linea))
        except queue.Full:
            return False
        h = self._escritor
        if h is None or not h.is_alive():
            h = threading.Thread(target=self._escribir, name="lune-mc-stdin", daemon=True)
            self._escritor = h
            h.start()
        return True

    def _escribir(self) -> None:
        yo = threading.current_thread()
        while True:
            try:
                item = self._cola.get(timeout=ESPERA_ESCRITOR_S)
            except queue.Empty:
                with self._lock:
                    if self._proceso is None and self._cola.empty():
                        if self._escritor is yo:
                            self._escritor = None
                        return
                continue
            try:
                p, linea = item
                try:
                    p.stdin.write(linea)
                    p.stdin.flush()
                except (OSError, ValueError, AttributeError):
                    self._roto_de = p
            finally:
                self._cola.task_done()

    def esperar_envios(self, tope_s: float = 2.0) -> bool:
        fin = time.monotonic() + max(0.0, float(tope_s))
        c = self._cola
        with c.all_tasks_done:
            while c.unfinished_tasks:
                quedan = fin - time.monotonic()
                if quedan <= 0:
                    return False
                c.all_tasks_done.wait(quedan)
        return True

    def enviar(self, msg: dict) -> bool:
        """Deja `msg` ({"tipo": …}) en la cola del escritor. Nunca bloquea. False si no hay
        bot, el tipo no vale, es demasiado grande o la cola está llena."""
        if not isinstance(msg, dict) or msg.get("tipo") not in TIPOS_A_BOT:
            return False
        try:
            linea = json.dumps(msg, ensure_ascii=True) + "\n"
        except (TypeError, ValueError):
            return False
        if len(linea) > MAX_ENTRADA:
            return False
        with self._lock:
            p = self._proceso
            if p is None or p is self._roto_de:
                return False
            try:
                if p.poll() is not None:
                    return False
            except Exception:
                return False
            return self._encolar(p, linea)

    def orden(self, id_: str, texto: str) -> bool:
        id_ = str(id_ or "")
        texto = str(texto or "").strip()[:200]
        if not _ID_ORDEN.fullmatch(id_) or not texto:
            return False
        return self.enviar({"tipo": "orden", "id": id_, "texto": texto})

    def decir(self, texto: str) -> bool:
        texto = re.sub(r"[\x00-\x1f\x7f]+", " ", str(texto or "")).strip()[:256]
        return bool(texto) and self.enviar({"tipo": "decir", "texto": texto})

    def pausa_llm(self, on: bool) -> bool:
        return self.enviar({"tipo": "pausa_llm", "on": bool(on)})

    def pausa_autonomo(self, on: bool) -> bool:
        return self.enviar({"tipo": "pausa_autonomo", "on": bool(on)})

    def pedir_estado(self) -> bool:
        return self.enviar({"tipo": "estado"})

    # ── Parar ──────────────────────────────────────────────────────────────────
    def parar(self, espera_s: float = 4.0) -> None:
        """salir → espera → cerrar stdin → terminate → matar el árbol. Idempotente; bloquea
        como mucho unos `espera_s` + 5 s (desde la interfaz, en un hilo)."""
        with self._lock:
            p = self._proceso
        if p is None:
            return
        try:
            vivo = p.poll() is None
        except Exception:
            vivo = False
        if vivo:
            self.enviar({"tipo": "salir"})
            self.esperar_envios(1.0)
            try:
                p.wait(timeout=max(0.0, float(espera_s)))
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
        with self._lock:
            if self._proceso is p:
                self._proceso = None            # el escritor, sin trabajo, se va solo
        if p.poll() is None and p.stdin is not None and self.esperar_envios(0.5):
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                p.wait(timeout=1.0)
            except Exception:
                pass
        with self._lock:
            job = self._jobs.get(id(p))
        if p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
        if p.poll() is None or job is not None:
            # El árbol entero: con un node.cmd, terminate() solo ha matado cmd.exe.
            matar_arbol(p, job, ejecutar=self._ejecutar)


__all__ = ("ProcesoBot", "config_bot", "config_llm", "nick_valido", "validar_host", "nick_desde_nombre",
           "version_node", "largo_utf16", "matar_arbol", "BOT_DIR", "MARCA", "MAX_LINEA", "TIPOS_BOT",
           "AVISO_INSTALAR", "AVISO_SIN_NODE", "AVISO_SIN_DUENO", "AVISO_BOT_VIVO", "ARGS_NPM_CI",
           "MARCA_INSTALANDO")
